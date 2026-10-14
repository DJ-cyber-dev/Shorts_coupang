"""Upload an existing Shorts Studio MP4 using YouTube OAuth."""
import argparse
import json
from pathlib import Path

from .youtube import UploadMetadata, YouTubeUploader, authenticated_service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("metadata", type=Path, help="JSON: title, description, tags, category_id, privacy_status, publish_at")
    parser.add_argument("--client-secrets", required=True, type=Path, help="Google OAuth Desktop app JSON")
    parser.add_argument("--allow-public", action="store_true", help="explicitly permit public upload")
    args = parser.parse_args()
    data = json.loads(args.metadata.read_text(encoding="utf-8"))
    metadata = UploadMetadata(
        title=data.get("title", ""), description=data.get("description", ""),
        tags=tuple(data.get("tags", [])), category_id=str(data.get("category_id", "22")),
        privacy_status=data.get("privacy_status", "private"), publish_at=data.get("publish_at"),
    )
    result = YouTubeUploader(authenticated_service(args.client_secrets)).upload(
        args.video, metadata, allow_public=args.allow_public, progress=lambda value: print(f"upload={value:.0%}"),
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
