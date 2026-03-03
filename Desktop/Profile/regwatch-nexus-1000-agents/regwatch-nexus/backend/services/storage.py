"""AWS S3 storage for reports and uploads"""
import boto3
from typing import Optional
from backend.config import settings

_s3 = None

def get_s3():
    global _s3
    if not _s3 and settings.AWS_ACCESS_KEY_ID:
        _s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
    return _s3


def upload_pdf(key: str, pdf_bytes: bytes) -> bool:
    s3 = get_s3()
    if not s3:
        print(f"[S3] Would upload {key} ({len(pdf_bytes)} bytes)")
        return True
    try:
        s3.put_object(Bucket=settings.AWS_S3_BUCKET, Key=key, 
                      Body=pdf_bytes, ContentType="application/pdf")
        return True
    except Exception as e:
        print(f"[S3] Upload error: {e}")
        return False


def get_presigned_url(key: str, expiry: int = 3600) -> Optional[str]:
    s3 = get_s3()
    if not s3:
        return f"https://{settings.AWS_S3_BUCKET}.s3.amazonaws.com/{key}"
    try:
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_S3_BUCKET, "Key": key},
            ExpiresIn=expiry,
        )
    except Exception as e:
        print(f"[S3] Presigned URL error: {e}")
        return None
