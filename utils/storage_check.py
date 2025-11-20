"""
Storage file existence check utilities.

Provides async functions to check if files exist in R2 and COS storage.
"""

import asyncio
import logging
import os
from typing import Tuple

logger = logging.getLogger(__name__)


async def check_r2_file_exists(object_key: str) -> bool:
    """
    Check if a file exists in Cloudflare R2 storage.

    Args:
        object_key: R2 object key (e.g., "audio/expressionss/abc123.mp3")

    Returns:
        True if file exists, False otherwise

    Examples:
        >>> import asyncio
        >>> exists = asyncio.run(check_r2_file_exists("audio/expressionss/test.mp3"))
        >>> isinstance(exists, bool)
        True
    """
    try:
        import aioboto3

        r2_config = {
            'bucket': os.getenv('R2_BUCKET_NAME'),
            'access_key_id': os.getenv('R2_ACCESS_KEY_ID'),
            'secret_access_key': os.getenv('R2_SECRET_ACCESS_KEY'),
            'endpoint_url': os.getenv('R2_ENDPOINT_URL')
        }

        if not all(r2_config.values()):
            logger.warning("R2 configuration incomplete, skipping check")
            return False

        session = aioboto3.Session()
        async with session.client(
            service_name='s3',
            endpoint_url=r2_config['endpoint_url'],
            aws_access_key_id=r2_config['access_key_id'],
            aws_secret_access_key=r2_config['secret_access_key'],
            region_name='auto'
        ) as s3_client:
            try:
                await s3_client.head_object(
                    Bucket=r2_config['bucket'],
                    Key=object_key
                )
                return True
            except s3_client.exceptions.NoSuchKey:
                return False
            except Exception as e:
                logger.debug(f"R2 file check failed for {object_key}: {e}")
                return False

    except ImportError:
        logger.warning("aioboto3 not installed, cannot check R2")
        return False
    except Exception as e:
        logger.error(f"R2 check error: {e}")
        return False


def check_cos_file_exists_sync(object_key: str) -> bool:
    """
    Check if a file exists in Tencent Cloud COS storage (synchronous).

    Args:
        object_key: COS object key (e.g., "audio/expressionss/abc123.mp3")

    Returns:
        True if file exists, False otherwise

    Examples:
        >>> exists = check_cos_file_exists_sync("audio/expressionss/test.mp3")
        >>> isinstance(exists, bool)
        True
    """
    try:
        from qcloud_cos import CosConfig, CosS3Client

        cos_config = {
            'secret_id': os.getenv('COS_SECRET_ID'),
            'secret_key': os.getenv('COS_SECRET_KEY'),
            'bucket': os.getenv('COS_BUCKET'),
            'region': os.getenv('COS_REGION')
        }

        if not all(cos_config.values()):
            logger.warning("COS configuration incomplete, skipping check")
            return False

        config = CosConfig(
            Region=cos_config['region'],
            SecretId=cos_config['secret_id'],
            SecretKey=cos_config['secret_key']
        )
        client = CosS3Client(config)

        try:
            response = client.head_object(
                Bucket=cos_config['bucket'],
                Key=object_key
            )
            return True
        except Exception as e:
            logger.debug(f"COS file does not exist {object_key}: {e}")
            return False

    except ImportError:
        logger.warning("qcloud_cos not installed, cannot check COS")
        return False
    except Exception as e:
        logger.error(f"COS check error: {e}")
        return False


async def check_cos_file_exists(object_key: str) -> bool:
    """
    Check if a file exists in Tencent Cloud COS storage (async wrapper).

    Args:
        object_key: COS object key (e.g., "audio/expressionss/abc123.mp3")

    Returns:
        True if file exists, False otherwise

    Examples:
        >>> import asyncio
        >>> exists = asyncio.run(check_cos_file_exists("audio/expressionss/test.mp3"))
        >>> isinstance(exists, bool)
        True
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, check_cos_file_exists_sync, object_key)


async def check_audio_exists_in_storage(
    object_key: str
) -> Tuple[bool, bool]:
    """
    Check if an audio file exists in both R2 and COS storage.

    Args:
        object_key: Object key for the audio file

    Returns:
        Tuple of (r2_exists, cos_exists)

    Examples:
        >>> import asyncio
        >>> r2, cos = asyncio.run(check_audio_exists_in_storage("audio/expressionss/test.mp3"))
        >>> isinstance(r2, bool) and isinstance(cos, bool)
        True
    """
    r2_exists, cos_exists = await asyncio.gather(
        check_r2_file_exists(object_key),
        check_cos_file_exists(object_key)
    )
    return r2_exists, cos_exists


__all__ = [
    'check_r2_file_exists',
    'check_cos_file_exists',
    'check_cos_file_exists_sync',
    'check_audio_exists_in_storage'
]
