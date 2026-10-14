import json
import queue
import sys
import threading
import time
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkinter.scrolledtext import ScrolledText
from pathlib import Path
from shorts_studio import __version__
from shorts_studio.core import Cancelled
from shorts_studio.jobs.history import JobHistory
from shorts_studio.pipeline import analyze_source, convert_source


def open_provider_settings(parent):
    from shorts_studio.providers.settings import ProviderSettings

    try:
        current = ProviderSettings.load()
    except (OSError, ValueError) as exc:
        messagebox.showerror("AI 설정", str(exc), parent=parent)
        return
    window = tk.Toplevel(parent)
    window.title("AI Provider 설정")
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=18)
    frame.pack(fill="both", expand=True)
    provider = tk.StringVar(value=current.provider)
    model = tk.StringVar(value=current.model)
    base_url = tk.StringVar(value=current.base_url)
    key_name = tk.StringVar(value=current.key_name)
    secret = tk.StringVar()
    fields = [
        ("Provider", provider, ("disabled", "openai-compatible")),
        ("Model", model, None),
        ("Base URL", base_url, None),
        ("API key 환경 변수 이름", key_name, None),
    ]
    for row, (label, variable, values) in enumerate(fields):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=5)
        if values:
            widget = ttk.Combobox(frame, textvariable=variable, values=values, state="readonly", width=44)
        else:
            widget = ttk.Entry(frame, textvariable=variable, width=47)
        widget.grid(row=row, column=1, sticky="ew", padx=(14, 0), pady=5)
    ttk.Label(frame, text="API key (선택 입력 · 설정 파일에 저장되지 않음)").grid(row=4, column=0, sticky="w", pady=5)
    ttk.Entry(frame, textvariable=secret, show="•", width=47).grid(row=4, column=1, sticky="ew", padx=(14, 0), pady=5)
    ttk.Label(frame, text="Windows에서는 Credential Manager에 저장합니다. 비 Windows 개발 환경은 key 환경 변수를 사용하세요.",
              wraplength=500).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 12))

    def current_settings():
        return ProviderSettings(provider.get(), model.get().strip(), base_url.get().strip(), key_name.get().strip())

    def save(*, close=True, notify=True):
        settings = current_settings()
        try:
            settings.validate()
            settings.save()
            if secret.get():
                settings.store_secret(secret.get())
            if notify:
                messagebox.showinfo("AI 설정", "Provider 설정을 저장했습니다.", parent=window)
            if close:
                window.destroy()
            return settings
        except (OSError, RuntimeError, ValueError, ImportError) as exc:
            messagebox.showerror("AI 설정", str(exc), parent=window)
            return None

    def test_connection():
        if not messagebox.askyesno("Provider 연결 확인", "설정된 Provider에 짧은 테스트 요청 1회를 전송합니다. 계속할까요?", parent=window):
            return
        settings = save(close=False, notify=False)
        if settings is None:
            return
        connection_button.configure(state="disabled")

        def check():
            try:
                from shorts_studio.providers.openai_compatible import OpenAICompatibleClient
                OpenAICompatibleClient(settings, timeout=30).complete([{"role": "user", "content": "Reply with OK."}], temperature=0)
                result = (True, "Provider 연결에 성공했습니다.")
            except Exception as exc:
                result = (False, str(exc))
            def show_result():
                if not window.winfo_exists():
                    return
                connection_button.configure(state="normal")
                (messagebox.showinfo if result[0] else messagebox.showerror)("Provider 연결 확인", result[1], parent=window)
            window.after(0, show_result)

        threading.Thread(target=check, daemon=True).start()

    ttk.Button(frame, text="저장", command=save).grid(row=6, column=1, sticky="e")
    connection_button = ttk.Button(frame, text="연결 확인", command=test_connection)
    connection_button.grid(row=6, column=0, sticky="w")


def open_tts_settings(parent):
    from shorts_studio.narration.settings import TTSSettings

    try:
        current = TTSSettings.load()
    except (OSError, ValueError) as exc:
        messagebox.showerror("TTS 설정", str(exc), parent=parent)
        return
    window = tk.Toplevel(parent)
    window.title("한국어 TTS 설정")
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=18)
    frame.pack(fill="both", expand=True)
    provider = tk.StringVar(value=current.provider)
    voice = tk.StringVar(value=current.voice)
    fields = [
        ("TTS 방식", provider, ("windows-local", "disabled")),
        ("Windows 음성", voice, None),
    ]
    for row, (label, variable, values) in enumerate(fields):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=5)
        widget = (ttk.Combobox(frame, textvariable=variable, values=values, state="readonly", width=44)
                  if values else ttk.Entry(frame, textvariable=variable, width=47))
        widget.grid(row=row, column=1, sticky="ew", padx=(14, 0), pady=5)
    ttk.Label(frame, text="Windows 내장 Heami 음성을 무료·오프라인으로 사용합니다. WinRT 음성 합성은 MSIX 설치본에서만 작동합니다.",
              wraplength=500).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 12))

    def save():
        try:
            settings = TTSSettings(provider.get(), voice=voice.get().strip())
            settings.validate()
            settings.save()
            messagebox.showinfo("TTS 설정", "Windows 로컬 TTS 설정을 저장했습니다.", parent=window)
            window.destroy()
        except (OSError, RuntimeError, ValueError, ImportError) as exc:
            messagebox.showerror("TTS 설정", str(exc), parent=window)

    ttk.Button(frame, text="저장", command=save).grid(row=8, column=1, sticky="e")


def open_source_settings(parent):
    from shorts_studio.sourcing.settings import YouTubeSearchSettings

    try:
        current = YouTubeSearchSettings.load()
    except (OSError, ValueError) as exc:
        messagebox.showerror("YouTube 소싱 설정", str(exc), parent=parent)
        return
    window = tk.Toplevel(parent)
    window.title("YouTube 후보 검색 설정")
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=18)
    frame.pack(fill="both", expand=True)
    key_name = tk.StringVar(value=current.key_name)
    secret = tk.StringVar()
    ttk.Label(frame, text="API key 환경 변수 이름").grid(row=0, column=0, sticky="w", pady=5)
    ttk.Entry(frame, textvariable=key_name, width=47).grid(row=0, column=1, padx=(14, 0), pady=5)
    ttk.Label(frame, text="YouTube Data API key (설정 파일에 저장되지 않음)").grid(row=1, column=0, sticky="w", pady=5)
    ttk.Entry(frame, textvariable=secret, show="•", width=47).grid(row=1, column=1, padx=(14, 0), pady=5)
    ttk.Label(frame, text="Windows에서는 Credential Manager에 저장합니다.",
              wraplength=500).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 12))

    def save():
        try:
            settings = YouTubeSearchSettings(key_name.get().strip())
            settings.save()
            if secret.get():
                settings.store_secret(secret.get())
            messagebox.showinfo("YouTube 소싱 설정", "검색 설정을 저장했습니다.", parent=window)
            window.destroy()
        except (OSError, RuntimeError, ValueError, ImportError) as exc:
            messagebox.showerror("YouTube 소싱 설정", str(exc), parent=window)

    ttk.Button(frame, text="저장", command=save).grid(row=3, column=1, sticky="e")


def open_tiktok_commercial_settings(parent):
    from shorts_studio.sourcing.tiktok_settings import TikTokCommercialSettings

    try:
        current = TikTokCommercialSettings.load()
    except (OSError, ValueError) as exc:
        messagebox.showerror("TikTok 광고 검색 설정", str(exc), parent=parent)
        return
    window = tk.Toplevel(parent)
    window.title("TikTok Commercial Content API 설정")
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=18)
    frame.pack(fill="both", expand=True)
    client_key_name = tk.StringVar(value=current.client_key_name)
    client_secret_name = tk.StringVar(value=current.client_secret_name)
    client_key, client_secret = tk.StringVar(), tk.StringVar()
    fields = (
        ("Client key 환경 변수 이름", client_key_name),
        ("Client secret 환경 변수 이름", client_secret_name),
    )
    for row, (label, variable) in enumerate(fields):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=variable, width=48).grid(row=row, column=1, padx=(14, 0), pady=5)
    ttk.Label(frame, text="승인 Client key").grid(row=2, column=0, sticky="w", pady=5)
    ttk.Entry(frame, textvariable=client_key, width=48).grid(row=2, column=1, padx=(14, 0), pady=5)
    ttk.Label(frame, text="승인 Client secret").grid(row=3, column=0, sticky="w", pady=5)
    ttk.Entry(frame, textvariable=client_secret, show="•", width=48).grid(row=3, column=1, padx=(14, 0), pady=5)
    ttk.Label(frame, text="설정은 환경 변수 이름만 저장합니다. Windows secret은 Credential Manager에 저장합니다. API 승인 필요.",
              wraplength=540).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 12))

    def save():
        try:
            settings = TikTokCommercialSettings(client_key_name.get().strip(), client_secret_name.get().strip())
            settings.save()
            if client_key.get() or client_secret.get():
                settings.store_secrets(client_key.get(), client_secret.get())
            messagebox.showinfo("TikTok 광고 검색 설정", "설정을 저장했습니다.", parent=window)
            window.destroy()
        except (OSError, RuntimeError, ValueError, ImportError) as exc:
            messagebox.showerror("TikTok 광고 검색 설정", str(exc), parent=window)

    ttk.Button(frame, text="저장", command=save).grid(row=5, column=1, sticky="e")


def open_coupang_settings(parent):
    from shorts_studio.products.coupang import CoupangCredentials

    window = tk.Toplevel(parent)
    window.title("Coupang Partners API 설정")
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=18)
    frame.pack(fill="both", expand=True)
    access_key, secret_key = tk.StringVar(), tk.StringVar()
    ttk.Label(frame, text="Access Key").grid(row=0, column=0, sticky="w", pady=5)
    ttk.Entry(frame, textvariable=access_key, width=48).grid(row=0, column=1, padx=(14, 0), pady=5)
    ttk.Label(frame, text="Secret Key").grid(row=1, column=0, sticky="w", pady=5)
    ttk.Entry(frame, textvariable=secret_key, show="•", width=48).grid(row=1, column=1, padx=(14, 0), pady=5)
    ttk.Label(frame, text="정상 활동으로 최종 승인된 Partners 계정의 key만 입력하세요. Windows Credential Manager에 저장하며, 검색은 시간당 최대 10회로 제한합니다.",
              wraplength=500).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 12))

    def save():
        try:
            CoupangCredentials.store(access_key.get(), secret_key.get())
        except (RuntimeError, ValueError, ImportError) as exc:
            messagebox.showerror("Coupang Partners API 설정", str(exc), parent=window)
            return
        messagebox.showinfo("Coupang Partners API 설정", "API key를 Windows Credential Manager에 저장했습니다.", parent=window)
        window.destroy()

    ttk.Button(frame, text="Credential Manager에 저장", command=save).grid(row=3, column=1, sticky="e")
    window.transient(parent)
    window.grab_set()
    parent.wait_window(window)


def open_update_settings(parent):
    from shorts_studio.updates.settings import GitHubUpdateSettings

    try:
        current = GitHubUpdateSettings.load()
    except (OSError, ValueError) as exc:
        messagebox.showerror("업데이트 설정", str(exc), parent=parent)
        return
    window = tk.Toplevel(parent)
    window.title("GitHub 업데이트 설정")
    window.resizable(False, False)
    frame = ttk.Frame(window, padding=18)
    frame.pack(fill="both", expand=True)
    repository = tk.StringVar(value=current.repository)
    public_key = tk.StringVar(value=current.public_key)
    ttk.Label(frame, text="GitHub 저장소 (owner/repo)").grid(row=0, column=0, sticky="w", pady=5)
    ttk.Entry(frame, textvariable=repository, width=55).grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=5)
    ttk.Label(frame, text="업데이트 서명 검증 공개키 (base64 Ed25519)").grid(row=1, column=0, sticky="w", pady=5)
    ttk.Entry(frame, textvariable=public_key, width=55).grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=5)
    ttk.Label(frame, text="GitHub Release에 서명 manifest와 Portable ZIP이 있어야 업데이트를 확인할 수 있습니다.",
              wraplength=540).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 12))

    def save():
        settings = GitHubUpdateSettings(repository.get().strip(), public_key.get().strip())
        try:
            settings.validate()
            settings.save()
        except (OSError, ValueError) as exc:
            messagebox.showerror("업데이트 설정", str(exc), parent=window)
            return
        messagebox.showinfo("업데이트 설정", "GitHub 업데이트 설정을 저장했습니다.", parent=window)
        window.destroy()

    ttk.Button(frame, text="저장", command=save).grid(row=3, column=1, sticky="e", pady=(4, 0))
    window.transient(parent)
    window.grab_set()
    parent.wait_window(window)


def legacy_main():
    if getattr(sys, "frozen", False):
        app_dir = Path(sys.executable).parent
        ffmpeg = app_dir / "ffmpeg" / "ffmpeg.exe"
        ffprobe = app_dir / "ffmpeg" / "ffprobe.exe"
        if ffmpeg.is_file():
            os.environ.setdefault("FFMPEG_BINARY", str(ffmpeg))
        if ffprobe.is_file():
            os.environ.setdefault("FFPROBE_BINARY", str(ffprobe))
    root = tk.Tk()
    root.title(f"Shorts Studio · {__version__}")
    root.geometry("760x660")
    root.minsize(680, 620)
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)
    source, output = tk.StringVar(), tk.StringVar()
    url, input_type = tk.StringVar(), tk.StringVar(value="url")
    mode, status = tk.StringVar(value="pad"), tk.StringVar(value="영상 URL과 저장 위치를 입력하세요.")
    events = queue.Queue()
    cancel = threading.Event()
    state = {"busy": False, "closing": False, "dialog_buttons": [], "source_candidate": None}
    job_history = JobHistory()
    recovered = job_history.reconcile_running()
    if recovered:
        status.set(f"이전 실행에서 중단된 작업 {recovered}개를 작업 기록에서 다시 실행할 수 있습니다.")

    def choose_source():
        name = filedialog.askopenfilename(filetypes=[("영상", "*.mp4 *.mov *.mkv *.avi *.webm"), ("모든 파일", "*.*")])
        if name:
            state["source_candidate"] = None
            source.set(name)
            input_type.set("file")
            path = Path(name)
            output.set(str(path.with_name(path.stem + "_shorts.mp4")))

    def choose_output():
        name = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4", "*.mp4")])
        if name:
            output.set(name)

    ttk.Label(frame, text="Shorts Studio", font=("Segoe UI", 20, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 16))
    widgets = []
    ttk.Button(frame, text="AI Provider 설정", command=lambda: open_provider_settings(root)).grid(row=0, column=1, sticky="e")
    ttk.Button(frame, text="TTS 설정", command=lambda: open_tts_settings(root)).grid(row=0, column=2, sticky="e")
    ttk.Button(frame, text="YouTube API 설정", command=lambda: open_source_settings(root)).grid(row=1, column=2, sticky="e")
    for column, (label, value) in enumerate([("URL", "url"), ("로컬 파일", "file")]):
        button = ttk.Radiobutton(frame, text=label, variable=input_type, value=value)
        button.grid(row=1, column=column, sticky="w")
        widgets.append(button)
    ttk.Label(frame, text="영상 URL").grid(row=2, column=0, sticky="w")
    entry = ttk.Entry(frame, textvariable=url)
    entry.grid(row=2, column=1, columnspan=2, sticky="ew", padx=8, pady=6)
    widgets.append(entry)
    for row, (label, var, command) in enumerate([("원본 파일", source, choose_source), ("저장 위치", output, choose_output)], 3):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w")
        entry = ttk.Entry(frame, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", padx=8, pady=6)
        button = ttk.Button(frame, text="선택", command=command)
        button.grid(row=row, column=2)
        widgets.extend([entry, button])
    for row, (label, value) in enumerate([("여백 추가 · 전체 화면 유지", "pad"), ("중앙 Crop · 화면 채우기", "crop")], 5):
        widget = ttk.Radiobutton(frame, text=label, variable=mode, value=value)
        widget.grid(row=row, column=1, sticky="w")
        widgets.append(widget)
    ttk.Label(frame, text="✓ 전체 화면 문자 제거 · 한글/영문/중국어 등").grid(row=7, column=0, columnspan=3, sticky="w", pady=8)
    progress = ttk.Progressbar(frame, maximum=1)
    progress.grid(row=8, column=0, columnspan=3, sticky="ew")
    ttk.Label(frame, textvariable=status).grid(row=9, column=0, columnspan=3, sticky="w", pady=8)

    def work(reference, target, remote, resize, source_candidate=None, job_id=None):
        metadata_path = Path(target).with_suffix(".source.json")
        metadata_written = False
        try:
            if source_candidate and metadata_path.exists():
                raise ValueError(f"출처 메타데이터 파일이 이미 있습니다: {metadata_path}")
            if source_candidate:
                metadata_path.parent.mkdir(parents=True, exist_ok=True)
                metadata_path.write_text(json.dumps(source_candidate, ensure_ascii=False, indent=2), encoding="utf-8")
                metadata_written = True
            result = convert_source(reference, target, is_url=remote, mode=resize,
                                    progress=lambda value: events.put(("job_progress", (job_id, value))) if job_id else events.put(("progress", value)),
                                    status=lambda value: events.put(("job_stage", (job_id, value))) if job_id else events.put(("status", value)), cancel=cancel)
            events.put(("done", (job_id, str(result))))
        except Cancelled:
            if metadata_written:
                metadata_path.unlink(missing_ok=True)
            events.put(("cancelled", (job_id, "취소되었습니다.")))
        except Exception as exc:
            if metadata_written:
                metadata_path.unlink(missing_ok=True)
            events.put(("error", (job_id, str(exc))))

    def work_analysis(reference, remote):
        try:
            result = analyze_source(reference, is_url=remote,
                                    status=lambda value: events.put(("status", value)), cancel=cancel)
            events.put(("analysis_done", json.dumps(result, ensure_ascii=False, indent=2)))
        except Cancelled:
            events.put(("cancelled", "취소되었습니다."))
        except Exception as exc:
            events.put(("error", str(exc)))

    def work_script(analysis, duration, tone):
        try:
            from shorts_studio.narration.script import KoreanShortsScriptWriter
            result = KoreanShortsScriptWriter().generate(analysis, duration_sec=duration, tone=tone)
            events.put(("script_done", json.dumps(result, ensure_ascii=False, indent=2)))
        except Exception as exc:
            events.put(("error", str(exc)))

    def work_tts(cleaned, script, target):
        try:
            from shorts_studio.narration.render import NarrationRenderer
            result = NarrationRenderer().render(cleaned, script, target)
            events.put(("tts_done", str(result)))
        except Exception as exc:
            events.put(("error", str(exc)))

    def work_upload(video, client_secrets, metadata, allow_public):
        try:
            from shorts_studio.upload.youtube import YouTubeUploader, authenticated_service
            service = authenticated_service(client_secrets)
            result = YouTubeUploader(service).upload(
                video, metadata, allow_public=allow_public,
                progress=lambda value: events.put(("upload_progress", value)),
            )
            events.put(("upload_done", json.dumps(result, ensure_ascii=False)))
        except Exception as exc:
            events.put(("error", str(exc)))

    def work_source_search(keyword):
        try:
            from dataclasses import asdict
            from shorts_studio.sourcing.youtube_search import YouTubeSourceSearch
            candidates = YouTubeSourceSearch().search(keyword)
            events.put(("source_candidates", json.dumps([asdict(item) for item in candidates], ensure_ascii=False)))
        except Exception as exc:
            events.put(("error", str(exc)))

    def work_tiktok_commercial_search(keyword, country):
        try:
            from dataclasses import asdict
            from shorts_studio.sourcing.tiktok_commercial import TikTokCommercialSearch
            candidates = TikTokCommercialSearch().search(keyword, country=country)
            events.put(("tiktok_ad_candidates", json.dumps([asdict(item) for item in candidates], ensure_ascii=False)))
        except Exception as exc:
            events.put(("tiktok_ad_search_error", str(exc)))

    def work_check_update():
        try:
            from shorts_studio.updates.github_release import GitHubReleaseUpdater
            events.put(("update_check_done", GitHubReleaseUpdater().check_latest()))
        except Exception as exc:
            events.put(("update_error", str(exc)))

    def work_apply_update(release):
        try:
            from shorts_studio.updates.github_release import GitHubReleaseUpdater
            GitHubReleaseUpdater().download_and_launch(release)
            events.put(("update_started", release.version))
        except Exception as exc:
            events.put(("update_error", str(exc)))

    def work_coupang_search(keyword):
        try:
            from shorts_studio.products import rank_products
            from shorts_studio.products.coupang import CoupangCredentials, CoupangPartnersClient
            credentials = CoupangCredentials.load()
            if credentials is None:
                raise RuntimeError("Coupang Partners API key가 없습니다. 먼저 API 설정을 완료하세요.")
            products = CoupangPartnersClient(credentials).search(keyword)
            matches = rank_products(keyword, products)
            events.put(("product_candidates", (keyword, matches)))
        except Exception as exc:
            events.put(("product_search_error", str(exc)))

    def save_json(document, parent, title):
        try:
            parsed = json.loads(document)
            target = filedialog.asksaveasfilename(
                parent=parent, defaultextension=".json", filetypes=[("JSON", "*.json")])
            if not target:
                return
            Path(target).write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            messagebox.showinfo(title, "JSON 파일을 저장했습니다.", parent=parent)
        except (OSError, ValueError) as exc:
            messagebox.showerror(title, f"JSON 형식 또는 저장 위치를 확인하세요.\n{exc}", parent=parent)

    def begin_script(analysis, parent, button):
        try:
            analysis = json.loads(analysis)
        except ValueError as exc:
            messagebox.showerror("대본 생성", f"분석 JSON을 확인하세요.\n{exc}", parent=parent)
            return
        duration = simpledialog.askinteger("대본 길이", "목표 길이 (초, 10~60)",
                                           initialvalue=30, minvalue=10, maxvalue=60, parent=parent)
        if duration is None:
            return
        tone = simpledialog.askstring("대본 말투", "friendly / review / informative / hook",
                                      initialvalue="friendly", parent=parent)
        if tone is None:
            return
        tone = tone.strip().lower()
        if tone not in {"friendly", "review", "informative", "hook"}:
            messagebox.showerror("대본 생성", "friendly, review, informative, hook 중에서 선택하세요.", parent=parent)
            return
        state["busy"] = True
        cancel.clear()
        for widget in widgets:
            widget.configure(state="disabled")
        start_button.configure(state="disabled")
        analysis_button.configure(state="disabled")
        cancel_button.configure(state="disabled")
        button.configure(state="disabled")
        state["dialog_buttons"].append(button)
        status.set("한국어 대본 생성 중…")
        threading.Thread(target=work_script, args=(analysis, duration, tone), daemon=True).start()

    def show_analysis(document):
        window = tk.Toplevel(root)
        window.title("AI 영상 분석 결과 · JSON 편집 가능")
        window.geometry("760x560")
        editor = ScrolledText(window, wrap="word", font=("Consolas", 10))
        editor.pack(fill="both", expand=True, padx=12, pady=12)
        editor.insert("1.0", document)

        buttons = ttk.Frame(window)
        buttons.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(buttons, text="JSON 저장", command=lambda: save_json(editor.get("1.0", "end-1c"), window, "AI 분석")).pack(side="right")
        draft = ttk.Button(buttons, text="한국어 대본 만들기",
                           command=lambda: begin_script(editor.get("1.0", "end-1c"), window, draft))
        draft.pack(side="right", padx=(0, 8))

    def show_script(document):
        window = tk.Toplevel(root)
        window.title("한국어 Shorts 대본 · JSON 편집 가능")
        window.geometry("760x560")
        editor = ScrolledText(window, wrap="word", font=("Consolas", 10))
        editor.pack(fill="both", expand=True, padx=12, pady=12)
        editor.insert("1.0", document)
        buttons = ttk.Frame(window)
        buttons.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(buttons, text="JSON 저장", command=lambda: save_json(editor.get("1.0", "end-1c"), window, "대본")).pack(side="right")

        def render_voice():
            try:
                script = json.loads(editor.get("1.0", "end-1c"))
            except ValueError as exc:
                messagebox.showerror("TTS 합성", f"대본 JSON을 확인하세요.\n{exc}", parent=window)
                return
            cleaned = Path(output.get()) if output.get() else None
            try:
                from shorts_studio.narration.render import _clean_source
                if not cleaned or not cleaned.is_file():
                    cleaned_name = filedialog.askopenfilename(parent=window, title="문자 제거 완료 영상 선택",
                                                             filetypes=[("MP4", "*.mp4")])
                    cleaned = Path(cleaned_name) if cleaned_name else None
                if not cleaned:
                    return
                _clean_source(cleaned)
            except (OSError, ValueError, RuntimeError) as exc:
                messagebox.showerror("TTS 합성", str(exc), parent=window)
                return
            target_name = filedialog.asksaveasfilename(
                parent=window, defaultextension=".mp4", initialfile=f"{cleaned.stem}_final.mp4",
                filetypes=[("MP4", "*.mp4")])
            if not target_name:
                return
            if not messagebox.askyesno("TTS 합성", "대본 문장을 이 PC의 Windows Heami 음성으로 합성합니다. 계속할까요?", parent=window):
                return
            state["busy"] = True
            cancel.clear()
            for widget in widgets:
                widget.configure(state="disabled")
            start_button.configure(state="disabled")
            analysis_button.configure(state="disabled")
            cancel_button.configure(state="disabled")
            voice_button.configure(state="disabled")
            state["dialog_buttons"].append(voice_button)
            status.set("한국어 음성·자막 합성 중…")
            threading.Thread(target=work_tts, args=(cleaned, script, Path(target_name)), daemon=True).start()

        voice_button = ttk.Button(buttons, text="TTS·자막 영상 만들기", command=render_voice)
        voice_button.pack(side="right", padx=(0, 8))

    def show_source_candidates(document):
        candidates = json.loads(document)
        window = tk.Toplevel(root)
        window.title("YouTube Creative Commons 후보")
        window.geometry("780x420")
        ttk.Label(window, text="검색 결과는 Creative Commons license로 필터링했습니다. 출처를 확인하고 사용할 후보를 선택하세요.",
                  wraplength=740).pack(anchor="w", padx=12, pady=8)
        columns = ("title", "channel", "license")
        table = ttk.Treeview(window, columns=columns, show="headings", selectmode="browse")
        table.heading("title", text="영상 제목")
        table.heading("channel", text="채널")
        table.heading("license", text="License")
        table.column("title", width=440)
        table.column("channel", width=220)
        table.column("license", width=110)
        table.pack(fill="both", expand=True, padx=12, pady=8)
        for index, item in enumerate(candidates):
            table.insert("", "end", iid=str(index), values=(item["title"], item["channel"], item["license"]))

        def apply_candidate():
            selected = table.selection()
            if not selected:
                messagebox.showinfo("후보 선택", "사용할 영상을 선택하세요.", parent=window)
                return
            item = candidates[int(selected[0])]
            url.set(item["url"])
            input_type.set("url")
            source.set(item["title"] + " — " + item["channel"])
            state["source_candidate"] = item
            messagebox.showinfo("후보 선택", "URL을 입력란에 넣었습니다. 제작 시작을 눌러 다운로드 및 필수 문자 제거를 실행하세요.", parent=window)
            window.destroy()

        footer = ttk.Frame(window)
        footer.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(footer, text="URL 사용", command=apply_candidate).pack(side="right")
        ttk.Label(footer, text=f"{len(candidates)}개 후보 · 선택 후에만 다운로드합니다.").pack(side="left")

    def search_sources():
        keyword = simpledialog.askstring("YouTube 후보 검색", "검색할 제품/영상 키워드 (YouTube Data API)", parent=root)
        if keyword is None:
            return
        if not keyword.strip():
            messagebox.showerror("YouTube 후보 검색", "검색어를 입력하세요.")
            return
        if not messagebox.askyesno("YouTube 후보 검색", "Creative Commons 및 4분 미만 영상 후보를 최대 10개 검색합니다. 진행할까요?"):
            return
        state["busy"] = True
        for widget in widgets:
            widget.configure(state="disabled")
        start_button.configure(state="disabled")
        analysis_button.configure(state="disabled")
        source_search_button.configure(state="disabled")
        cancel_button.configure(state="disabled")
        status.set("YouTube 후보 검색 중…")
        threading.Thread(target=work_source_search, args=(keyword.strip(),), daemon=True).start()

    def show_tiktok_ad_candidates(document):
        candidates = json.loads(document)
        window = tk.Toplevel(root)
        window.title("TikTok EEA 광고 라이브러리 · 참고 후보")
        window.geometry("820x430")
        ttk.Label(window, text="상업 콘텐츠 광고 검색 결과이며 일반 organic 영상 검색이 아닙니다. 공개 광고라도 Shorts 재사용 권리는 별도로 확인해야 합니다.",
                  wraplength=780).pack(anchor="w", padx=12, pady=8)
        columns = ("advertiser", "ad_id", "date", "reach", "country")
        table = ttk.Treeview(window, columns=columns, show="headings", selectmode="browse")
        for col, title, width in (("advertiser", "Advertiser", 220), ("ad_id", "Ad ID", 140),
                                  ("date", "게시 기간", 190), ("reach", "도달 범위", 120),
                                  ("country", "국가", 80)):
            table.heading(col, text=title)
            table.column(col, width=width)
        table.pack(fill="both", expand=True, padx=12, pady=8)
        for index, item in enumerate(candidates):
            table.insert("", "end", iid=str(index), values=(
                item["advertiser"], item["ad_id"],
                f"{item['first_shown_date']} ~ {item['last_shown_date']}",
                item["reach"], item["country"],
            ))

        def show_details(_event=None):
            selected = table.selection()
            if not selected:
                return
            item = candidates[int(selected[0])]
            media = "\n".join(item["video_urls"] + item["image_urls"]) or "제공된 preview URL 없음"
            messagebox.showinfo(
                "광고 참고 정보",
                f"Advertiser: {item['advertiser']}\nPaid by: {item['paid_by']}\n"
                f"Status: {item['status']} · Reach: {item['reach']}\n"
                f"참고용 media URL:\n{media}\n\n{item['usage']}",
                parent=window,
            )

        table.bind("<Double-1>", show_details)
        footer = ttk.Frame(window)
        footer.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(footer, text="선택 광고 정보", command=show_details).pack(side="right")
        ttk.Label(footer, text=f"{len(candidates)}개 참고 후보 · 광고 소재 검색은 EEA 국가 데이터에 한정").pack(side="left")

    def search_tiktok_ads():
        keyword = simpledialog.askstring("TikTok 광고 참고 검색", "검색어 (최대 50자)", parent=root)
        if keyword is None:
            return
        keyword = keyword.strip()
        if not keyword:
            messagebox.showerror("TikTok 광고 참고 검색", "검색어를 입력하세요.", parent=root)
            return
        country = simpledialog.askstring(
            "EEA 광고 국가", "검색 대상 EEA 국가 코드 (예: FR, DE, IT)", initialvalue="FR", parent=root
        )
        if country is None:
            return
        country = country.strip().upper()
        if not messagebox.askyesno(
            "TikTok 광고 참고 검색",
            f"승인된 Commercial Content API로 {country} 대상 광고를 최대 10개 검색합니다.\n"
            "결과는 광고 참고 자료이며 콘텐츠 재사용 권한을 의미하지 않습니다. 계속할까요?",
            parent=root,
        ):
            return
        state["busy"] = True
        for widget in widgets:
            widget.configure(state="disabled")
        start_button.configure(state="disabled")
        analysis_button.configure(state="disabled")
        cancel_button.configure(state="disabled")
        status.set("TikTok 광고 참고 검색 중…")
        threading.Thread(target=work_tiktok_commercial_search, args=(keyword, country), daemon=True).start()

    def match_products():
        query = simpledialog.askstring("쿠팡 상품 매칭", "영상/대본에서 찾을 상품 키워드", parent=root)
        if query is None:
            return
        query = query.strip()
        if not query:
            messagebox.showerror("쿠팡 상품 매칭", "검색어를 입력하세요.", parent=root)
            return
        use_api = messagebox.askyesnocancel("쿠팡 상품 매칭", "예: Coupang Partners API로 검색\n아니오: 후보 JSON 파일 열기", parent=root)
        if use_api is None:
            return
        if use_api:
            try:
                from shorts_studio.products.coupang import CoupangCredentials
                if CoupangCredentials.load() is None:
                    open_coupang_settings(root)
                    if CoupangCredentials.load() is None:
                        return
            except (ImportError, RuntimeError) as exc:
                messagebox.showerror("Coupang 상품 검색", str(exc), parent=root)
                return
            state["busy"] = True
            for widget in widgets:
                widget.configure(state="disabled")
            start_button.configure(state="disabled")
            analysis_button.configure(state="disabled")
            cancel_button.configure(state="disabled")
            status.set("Coupang 상품 후보 검색 중…")
            threading.Thread(target=work_coupang_search, args=(query,), daemon=True).start()
            return
        candidate_path = filedialog.askopenfilename(
            title="상품 후보 JSON 선택",
            filetypes=[("JSON", "*.json"), ("모든 파일", "*.*")], parent=root,
        )
        if not candidate_path:
            return
        try:
            from shorts_studio.products import rank_products, read_product_candidates
            products = read_product_candidates(candidate_path)
            matches = rank_products(query, products)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            messagebox.showerror("쿠팡 상품 매칭", str(exc), parent=root)
            return
        show_product_candidates(query, matches)

    def show_product_candidates(query, matches):
        if not matches:
            messagebox.showinfo("쿠팡 상품 매칭", "검색어와 일치하는 상품 후보가 없습니다.", parent=root)
            return
        window = tk.Toplevel(root)
        window.title("쿠팡 상품 후보 선택")
        window.geometry("800x430")
        ttk.Label(window, text="상품 제목과 검색어의 일치도로 정렬했습니다. 상품 링크를 확인한 뒤 선택하세요.",
                  wraplength=770).pack(anchor="w", padx=12, pady=8)
        columns = ("title", "price", "score", "affiliate")
        table = ttk.Treeview(window, columns=columns, show="headings", selectmode="browse")
        for column, label, width in (("title", "상품명", 390), ("price", "가격", 100),
                                     ("score", "일치도", 90), ("affiliate", "파트너스 링크", 190)):
            table.heading(column, text=label)
            table.column(column, width=width)
        table.pack(fill="both", expand=True, padx=12, pady=8)
        for index, match in enumerate(matches):
            table.insert("", "end", iid=str(index), values=(
                match.product.title, match.product.price if match.product.price is not None else "",
                f"{match.score:.0%}", "있음" if match.product.affiliate_url else "없음",
            ))

        def save_match():
            selected = table.selection()
            if not selected:
                messagebox.showinfo("상품 선택", "사용할 상품 후보를 선택하세요.", parent=window)
                return
            match = matches[int(selected[0])]
            target = filedialog.asksaveasfilename(
                title="선택 상품 정보 저장", defaultextension=".json",
                filetypes=[("JSON", "*.json")], parent=window,
            )
            if not target:
                return
            document = {
                "query": query.strip(),
                "product": {
                    "id": match.product.id, "title": match.product.title,
                    "url": match.product.url, "affiliate_url": match.product.affiliate_url,
                    "price": match.product.price, "image_url": match.product.image_url,
                },
                "score": match.score, "matched_terms": list(match.matched_terms),
            }
            try:
                Path(target).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("상품 저장", str(exc), parent=window)
                return
            script_path = filedialog.askopenfilename(
                title="상품 정보를 연결할 한국어 대본 JSON 선택 (취소하면 상품 정보만 저장)",
                filetypes=[("JSON", "*.json"), ("모든 파일", "*.*")], parent=window,
            )
            if script_path:
                try:
                    from shorts_studio.products import attach_product_match
                    script = json.loads(Path(script_path).read_text(encoding="utf-8"))
                    linked = attach_product_match(script, match)
                except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                    messagebox.showerror("대본 연결", str(exc), parent=window)
                    return
                linked_target = filedialog.asksaveasfilename(
                    title="상품이 연결된 대본 저장",
                    initialdir=str(Path(script_path).parent),
                    initialfile=f"{Path(script_path).stem}_with_product.json",
                    defaultextension=".json", filetypes=[("JSON", "*.json")], parent=window,
                )
                if linked_target:
                    try:
                        Path(linked_target).write_text(
                            json.dumps(linked, ensure_ascii=False, indent=2), encoding="utf-8")
                    except OSError as exc:
                        messagebox.showerror("대본 연결", str(exc), parent=window)
                        return
                    messagebox.showinfo("상품 연결", f"상품·순위 근거를 대본 JSON에 연결했습니다.\n{linked_target}", parent=window)
                else:
                    messagebox.showinfo("상품 저장", f"상품 정보만 저장했습니다.\n{target}", parent=window)
            else:
                messagebox.showinfo("상품 저장", f"상품 정보만 저장했습니다.\n{target}", parent=window)
            window.destroy()

        footer = ttk.Frame(window)
        footer.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(footer, text="상품 선택·저장", command=save_match).pack(side="right")
        ttk.Label(footer, text=f"{len(matches)}개 후보 · 원본 후보 파일은 수정하지 않습니다.").pack(side="left")

    def upload_video():
        video = Path(output.get()) if output.get() else None
        if not video or not video.is_file():
            messagebox.showerror("YouTube 업로드", "먼저 제작된 MP4를 저장 위치에 생성하세요.", parent=root)
            return
        client_secrets = filedialog.askopenfilename(
            title="Google OAuth Desktop client JSON 선택",
            filetypes=[("JSON", "*.json"), ("모든 파일", "*.*")], parent=root,
        )
        if not client_secrets:
            return
        window = tk.Toplevel(root)
        window.title("YouTube 업로드 설정")
        window.geometry("600x440")
        window.transient(root)
        form = ttk.Frame(window, padding=16)
        form.pack(fill="both", expand=True)
        title_var = tk.StringVar(value=video.stem[:100])
        tags_var = tk.StringVar(value="shorts")
        privacy_var = tk.StringVar(value="private")
        publish_var = tk.StringVar()
        ttk.Label(form, text=f"영상: {video.name}").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(form, text="제목 (최대 100자)").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=title_var, width=55).grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Label(form, text="설명").grid(row=2, column=0, sticky="nw", pady=5)
        description = ScrolledText(form, width=50, height=8, wrap="word")
        description.grid(row=2, column=1, sticky="nsew", pady=5)
        ttk.Label(form, text="Tags · 쉼표 구분").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=tags_var, width=55).grid(row=3, column=1, sticky="ew", pady=5)
        ttk.Label(form, text="공개 범위").grid(row=4, column=0, sticky="w", pady=5)
        ttk.Combobox(form, textvariable=privacy_var, values=("private", "unlisted", "public"), state="readonly", width=52).grid(row=4, column=1, sticky="ew", pady=5)
        ttk.Label(form, text="예약 게시 시각 · ISO 8601, private만 가능").grid(row=5, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=publish_var, width=55).grid(row=5, column=1, sticky="ew", pady=5)
        ttk.Label(form, text="최초 실행 시 브라우저 OAuth 승인이 필요합니다. 기본 공개 범위는 private입니다.", wraplength=540).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 10))

        def submit_upload():
            from shorts_studio.upload.youtube import UploadMetadata
            metadata = UploadMetadata(
                title=title_var.get().strip(), description=description.get("1.0", "end-1c").strip(),
                tags=tuple(item.strip() for item in tags_var.get().split(",") if item.strip()),
                privacy_status=privacy_var.get(), publish_at=publish_var.get().strip() or None,
            )
            allow_public = metadata.privacy_status == "public"
            try:
                metadata.validate(allow_public=allow_public)
            except ValueError as exc:
                messagebox.showerror("YouTube 업로드", str(exc), parent=window)
                return
            if allow_public and not messagebox.askyesno("공개 업로드 확인", "선택한 채널에 이 영상을 공개로 게시합니다. 계속할까요?", parent=window):
                return
            if not messagebox.askyesno("YouTube 업로드", f"{video.name}을(를) {metadata.privacy_status}로 업로드합니다. 계속할까요?", parent=window):
                return
            state["busy"] = True
            for widget in widgets:
                widget.configure(state="disabled")
            start_button.configure(state="disabled")
            analysis_button.configure(state="disabled")
            source_search_button.configure(state="disabled")
            upload_button.configure(state="disabled")
            cancel_button.configure(state="disabled")
            progress["value"] = 0
            status.set("YouTube OAuth 연결 및 업로드 중…")
            window.destroy()
            threading.Thread(target=work_upload, args=(video, Path(client_secrets), metadata, allow_public), daemon=True).start()

        ttk.Button(form, text="업로드", command=submit_upload).grid(row=7, column=1, sticky="e", pady=(6, 0))
        form.columnconfigure(1, weight=1)
        form.rowconfigure(2, weight=1)

    def start():
        remote = input_type.get() == "url"
        reference = url.get().strip() if remote else source.get()
        if not reference or not output.get():
            messagebox.showerror("입력 확인", "URL 또는 원본 파일과 저장 위치를 선택하세요.")
            return
        state["busy"] = True
        cancel.clear()
        for widget in widgets:
            widget.configure(state="disabled")
        start_button.configure(state="disabled")
        cancel_button.configure(state="normal")
        progress["value"] = 0
        status.set("변환 중…")
        candidate = state["source_candidate"] if remote and state["source_candidate"] and reference == state["source_candidate"].get("url") else None
        target = Path(output.get())
        job = job_history.create(kind="video", source=reference, output=str(target))
        state["job_id"] = job["id"]
        state["last_job_write"] = 0.0
        threading.Thread(target=work, args=(reference, target, remote, mode.get(), candidate, job["id"])).start()

    def analyze():
        remote = input_type.get() == "url"
        reference = url.get().strip() if remote else source.get()
        if not reference:
            messagebox.showerror("입력 확인", "AI 분석할 URL 또는 로컬 영상 파일을 선택하세요.")
            return
        if not messagebox.askyesno("AI 영상 분석", "영상에서 추출한 최대 8장의 frame을 설정된 Provider로 전송합니다. 계속할까요?"):
            return
        state["busy"] = True
        cancel.clear()
        for widget in widgets:
            widget.configure(state="disabled")
        start_button.configure(state="disabled")
        analysis_button.configure(state="disabled")
        cancel_button.configure(state="normal")
        progress["value"] = 0
        status.set("AI 분석을 준비 중…")
        threading.Thread(target=work_analysis, args=(reference, remote), daemon=True).start()

    def restore_controls():
        state["busy"] = False
        for widget in widgets:
            widget.configure(state="normal")
        start_button.configure(state="normal")
        analysis_button.configure(state="normal")
        cancel_button.configure(state="disabled")
        for button in state.pop("dialog_buttons", []):
            try:
                button.configure(state="normal")
            except tk.TclError:
                pass
        state["dialog_buttons"] = []

    def check_for_updates():
        if state["busy"]:
            return
        state["busy"] = True
        for widget in widgets:
            widget.configure(state="disabled")
        start_button.configure(state="disabled")
        cancel_button.configure(state="disabled")
        status.set("서명된 GitHub Release를 확인 중…")
        threading.Thread(target=work_check_update, daemon=True).start()

    def offer_update(release):
        if release is None:
            status.set("최신 버전입니다.")
            messagebox.showinfo("Shorts Studio 업데이트", "현재 최신 버전을 사용 중입니다.", parent=root)
            return
        answer = messagebox.askyesno(
            "Shorts Studio 업데이트",
            f"버전 {release.version} 업데이트가 있습니다. 서명을 확인한 설치본을 내려받아 적용할까요?\n\n"
            f"{release.notes[:1200]}\n\n적용 시 앱이 종료된 뒤 다시 시작됩니다.",
            parent=root,
        )
        if not answer:
            return
        state["busy"] = True
        for widget in widgets:
            widget.configure(state="disabled")
        start_button.configure(state="disabled")
        cancel_button.configure(state="disabled")
        status.set(f"{release.version} 업데이트를 검증하고 다운로드 중…")
        threading.Thread(target=work_apply_update, args=(release,), daemon=True).start()

    def show_job_history():
        records = job_history.list_recent(100)
        window = tk.Toplevel(root)
        window.title("작업 기록 · 재실행 가능")
        window.geometry("820x420")
        ttk.Label(window, text="실행 중 종료된 작업은 중단 상태로 표시됩니다. 영상 작업을 선택하고 입력에 불러와 다시 실행하세요.",
                  wraplength=790).pack(anchor="w", padx=12, pady=8)
        columns = ("status", "stage", "source", "output")
        table = ttk.Treeview(window, columns=columns, show="headings", selectmode="browse")
        for column, title, width in (("status", "상태", 90), ("stage", "단계", 150), ("source", "입력", 270), ("output", "출력", 270)):
            table.heading(column, text=title)
            table.column(column, width=width)
        table.pack(fill="both", expand=True, padx=12, pady=8)
        record_by_id = {}
        for record in records:
            if record.get("kind") != "video":
                continue
            record_by_id[record["id"]] = record
            table.insert("", "end", iid=record["id"], values=(record.get("status"), record.get("stage"),
                         record.get("source"), record.get("output")))

        def load_job():
            selected = table.selection()
            if not selected:
                messagebox.showinfo("작업 기록", "다시 실행할 작업을 선택하세요.", parent=window)
                return
            record = record_by_id[selected[0]]
            reference = record.get("source", "")
            if not reference:
                messagebox.showerror("작업 기록", "입력 정보가 없어 다시 실행할 수 없습니다.", parent=window)
                return
            remote = reference.startswith("https://")
            input_type.set("url" if remote else "file")
            if remote:
                url.set(reference)
            else:
                source.set(reference)
            target = Path(record.get("output") or "shorts.mp4")
            if target.exists():
                target = target.with_name(f"{target.stem}_retry{target.suffix}")
            output.set(str(target))
            status.set("작업 입력을 불러왔습니다. 저장 위치를 확인하고 제작 시작을 누르세요.")
            window.destroy()

        footer = ttk.Frame(window)
        footer.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(footer, text="선택 작업 입력에 불러오기", command=load_job).pack(side="right")
        ttk.Label(footer, text=f"{len(record_by_id)}개 영상 작업 · job 정보는 이 PC의 ShortsStudio 설정 경로에 저장됩니다.").pack(side="left")

    def poll():
        while not events.empty():
            kind, value = events.get_nowait()
            if kind == "progress":
                progress["value"] = value
            elif kind == "job_progress":
                job_id, amount = value
                progress["value"] = amount
                now = time.monotonic()
                if job_id and (amount >= 1 or now - state.get("last_job_write", 0) >= 2):
                    job_history.update(job_id, progress=amount)
                    state["last_job_write"] = now
            elif kind == "job_stage":
                job_id, stage = value
                if job_id:
                    job_history.update(job_id, stage=stage)
                status.set(stage)
                progress["value"] = 0
            elif kind == "status":
                status.set(value)
                progress["value"] = 0
            elif kind == "analysis_done":
                restore_controls()
                status.set("AI 분석 완료 · 결과를 편집하고 JSON으로 저장할 수 있습니다.")
                if not state["closing"]:
                    show_analysis(value)
            elif kind == "script_done":
                restore_controls()
                status.set("한국어 대본 생성 완료 · 문장을 편집하고 TTS·자막을 합성할 수 있습니다.")
                if not state["closing"]:
                    show_script(value)
            elif kind == "tts_done":
                restore_controls()
                status.set(f"TTS 영상 합성 완료 · {value}")
                if not state["closing"]:
                    messagebox.showinfo("Shorts Studio", f"최종 영상이 저장되었습니다.\n{value}")
            elif kind == "source_candidates":
                restore_controls()
                status.set("YouTube 후보 검색 완료 · 사용할 영상을 선택하세요.")
                if not state["closing"]:
                    show_source_candidates(value)
            elif kind == "tiktok_ad_candidates":
                restore_controls()
                status.set("TikTok EEA 광고 참고 검색 완료 · 재사용 권리는 별도 확인하세요.")
                if not state["closing"]:
                    show_tiktok_ad_candidates(value)
            elif kind == "tiktok_ad_search_error":
                restore_controls()
                status.set("TikTok 광고 참고 검색 실패")
                if not state["closing"]:
                    messagebox.showerror("TikTok 광고 참고 검색", value, parent=root)
            elif kind == "update_check_done":
                restore_controls()
                offer_update(value)
            elif kind == "update_started":
                restore_controls()
                status.set("업데이트 적용을 위해 앱을 종료합니다…")
                root.after(400, close)
            elif kind == "update_error":
                restore_controls()
                status.set("업데이트 확인 또는 적용에 실패했습니다.")
                if not state["closing"]:
                    messagebox.showerror("Shorts Studio 업데이트", value, parent=root)
            elif kind == "product_candidates":
                restore_controls()
                query, matches = value
                status.set("Coupang 상품 검색 완료 · 후보를 선택하세요.")
                if not state["closing"]:
                    show_product_candidates(query, matches)
            elif kind == "product_search_error":
                restore_controls()
                status.set("Coupang 상품 검색 실패")
                if not state["closing"]:
                    messagebox.showerror("Coupang 상품 검색", value, parent=root)
            elif kind == "upload_progress":
                progress["value"] = value
                status.set(f"YouTube 업로드 중… {value:.0%}")
            elif kind == "upload_done":
                restore_controls()
                result = json.loads(value)
                status.set(f"YouTube 업로드 완료 · {result['url']}")
                if not state["closing"]:
                    messagebox.showinfo("YouTube 업로드 완료", result["url"], parent=root)
            else:
                job_id = None
                if kind == "done" and isinstance(value, tuple):
                    job_id, value = value
                    if job_id:
                        job_history.update(job_id, status="completed", stage="completed", progress=1.0)
                elif kind == "cancelled" and isinstance(value, tuple):
                    job_id, value = value
                    if job_id:
                        job_history.update(job_id, status="cancelled", stage="cancelled")
                elif kind == "error" and isinstance(value, tuple):
                    job_id, value = value
                    if job_id:
                        job_history.update(job_id, status="failed", stage="failed", error=value)
                restore_controls()
                status.set("완료 · 저장 폴더에서 결과와 문자 제거 비교 이미지를 확인하세요." if kind == "done" else "취소됨" if kind == "cancelled" else "변환 실패")
                if kind == "error" and not state["closing"]:
                    messagebox.showerror("작업 실패", value)
        if state["closing"] and not state["busy"]:
            root.destroy()
        else:
            root.after(100, poll)

    def close():
        state["closing"] = True
        cancel.set()
        status.set("작업을 정리하고 종료합니다…")

    start_button = ttk.Button(frame, text="제작 시작", command=start)
    start_button.grid(row=10, column=1, sticky="e")
    cancel_button = ttk.Button(frame, text="취소", command=cancel.set, state="disabled")
    cancel_button.grid(row=10, column=2)
    analysis_button = ttk.Button(frame, text="AI 영상 분석", command=analyze)
    analysis_button.grid(row=11, column=0, sticky="w", pady=8)
    widgets.append(analysis_button)
    source_search_button = ttk.Button(frame, text="YouTube 영상 찾기", command=search_sources)
    source_search_button.grid(row=11, column=2, sticky="e", pady=8)
    widgets.append(source_search_button)
    upload_button = ttk.Button(frame, text="YouTube 업로드", command=upload_video)
    upload_button.grid(row=12, column=2, sticky="e", pady=8)
    widgets.append(upload_button)
    product_button = ttk.Button(frame, text="쿠팡 상품 후보 선택", command=match_products)
    product_button.grid(row=13, column=1, sticky="e", pady=8)
    widgets.append(product_button)
    tiktok_settings_button = ttk.Button(frame, text="TikTok 광고 API 설정",
                                        command=lambda: open_tiktok_commercial_settings(root))
    tiktok_settings_button.grid(row=14, column=0, sticky="w", pady=8)
    tiktok_search_button = ttk.Button(frame, text="TikTok 광고 참고 검색", command=search_tiktok_ads)
    tiktok_search_button.grid(row=14, column=2, sticky="e", pady=8)
    widgets.append(tiktok_search_button)
    update_button = ttk.Button(frame, text="업데이트 확인", command=check_for_updates)
    update_button.grid(row=15, column=2, sticky="e", pady=8)
    widgets.append(update_button)
    update_settings_button = ttk.Button(frame, text="업데이트 설정",
                                        command=lambda: open_update_settings(root))
    update_settings_button.grid(row=15, column=0, sticky="w", pady=8)
    ttk.Button(frame, text="작업 기록", command=show_job_history).grid(row=12, column=0, sticky="w", pady=8)
    def show_preview():
        import os
        preview = Path(output.get()).with_suffix(".preview.jpg") if output.get() else None
        if preview and preview.is_file():
            os.startfile(str(preview.resolve()))
        else:
            messagebox.showinfo("미리보기", "제작 후 문자 탐지 영역이 있으면 비교 이미지가 생성됩니다.")
    ttk.Button(frame, text="문자 제거 비교 보기", command=show_preview).grid(row=11, column=1, sticky="e", pady=8)
    frame.columnconfigure(1, weight=1)
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(100, poll)
    root.mainloop()


def main():
    from shorts_studio.ui.web_app import main as web_main
    web_main()


if __name__ == "__main__":
    main()
