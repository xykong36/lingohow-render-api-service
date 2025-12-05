#!/usr/bin/env python3
"""
检查并生成指定 Episode 范围的音频文件脚本

功能：
1. 从 prod_lingohow-sentences-20251113.json 读取数据
2. 根据命令行参数筛选指定范围的 episode 句子
3. 检查每个句子的音频文件是否存在于 R2 和 COS
4. 将缺失音频的句子保存到 JSON 文件
5. 使用 edge-tts 生成缺失的音频文件
6. 上传音频文件到 R2 和 COS

性能优化：
- 文件检查：4 并发
- 音频生成：3 并发
- R2 上传：2 并发
- COS 上传：3 线程

使用方法：
    python check_and_generate_audio.py -s 238 -e 300
    python check_and_generate_audio.py --start 1 --end 100
"""

import asyncio
import json
import logging
import os
import hashlib
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime

# 导入现有的服务
try:
    from dotenv import load_dotenv
    load_dotenv(".env.local")
except ImportError:
    pass

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def generate_sentence_hash(text: str) -> str:
    """
    生成句子的哈希值（与 NextJS getAudioFileName 逻辑一致）

    Args:
        text: 句子文本

    Returns:
        MD5 哈希值（8位）
    """
    return hashlib.md5(text.strip().encode()).hexdigest()[:8]


async def get_all_audio_files_from_r2() -> set:
    """
    从 R2 获取所有音频文件列表（批量）

    Returns:
        包含所有文件名（不含路径和扩展名）的 Set
    """
    try:
        import aioboto3
        import os

        r2_config = {
            'bucket': os.getenv('R2_BUCKET_NAME'),
            'access_key_id': os.getenv('R2_ACCESS_KEY_ID'),
            'secret_access_key': os.getenv('R2_SECRET_ACCESS_KEY'),
            'endpoint_url': os.getenv('R2_ENDPOINT_URL')
        }

        if not all(r2_config.values()):
            logger.warning("R2 configuration incomplete, skipping")
            return set()

        existing_files = set()
        session = aioboto3.Session()

        async with session.client(
            service_name='s3',
            endpoint_url=r2_config['endpoint_url'],
            aws_access_key_id=r2_config['access_key_id'],
            aws_secret_access_key=r2_config['secret_access_key'],
            region_name='auto'
        ) as s3_client:
            continuation_token = None
            page_count = 0

            while True:
                list_params = {
                    'Bucket': r2_config['bucket'],
                    'Prefix': 'audio/sentences/',
                    'MaxKeys': 1000
                }

                if continuation_token:
                    list_params['ContinuationToken'] = continuation_token

                response = await s3_client.list_objects_v2(**list_params)
                page_count += 1

                # 提取文件名
                if 'Contents' in response:
                    for obj in response['Contents']:
                        key = obj.get('Key', '')
                        # 去掉 'audio/sentences/' 前缀和 '.mp3' 后缀
                        filename = key.replace('audio/sentences/', '').replace('.mp3', '')
                        if filename:
                            existing_files.add(filename)

                # 检查是否还有更多数据
                if response.get('IsTruncated'):
                    continuation_token = response.get('NextContinuationToken')
                else:
                    break

            logger.info(f"✅ R2: 加载了 {len(existing_files)} 个音频文件（{page_count} 页）")
            return existing_files

    except ImportError:
        logger.warning("aioboto3 未安装，无法检查 R2")
        return set()
    except Exception as e:
        logger.error(f"从 R2 获取文件列表失败: {e}")
        return set()


def _get_cos_files_sync() -> set:
    """
    从 COS 获取所有音频文件列表（同步版本）

    Returns:
        包含所有文件名（不含路径和扩展名）的 Set
    """
    try:
        from qcloud_cos import CosConfig, CosS3Client
        import os

        cos_config = {
            'secret_id': os.getenv('COS_SECRET_ID'),
            'secret_key': os.getenv('COS_SECRET_KEY'),
            'bucket': os.getenv('COS_BUCKET'),
            'region': os.getenv('COS_REGION')
        }

        if not all(cos_config.values()):
            logger.warning("COS configuration incomplete, skipping")
            return set()

        config = CosConfig(
            Region=cos_config['region'],
            SecretId=cos_config['secret_id'],
            SecretKey=cos_config['secret_key']
        )
        client = CosS3Client(config)

        existing_files = set()
        marker = ''
        page_count = 0

        while True:
            response = client.list_objects(
                Bucket=cos_config['bucket'],
                Prefix='audio/sentences/',
                Marker=marker,
                MaxKeys=1000
            )
            page_count += 1

            # 提取文件名
            if 'Contents' in response:
                for obj in response['Contents']:
                    key = obj.get('Key', '')
                    # 去掉 'audio/sentences/' 前缀和 '.mp3' 后缀
                    filename = key.replace('audio/sentences/', '').replace('.mp3', '')
                    if filename:
                        existing_files.add(filename)

            # 检查是否还有更多数据
            if response.get('IsTruncated') == 'true':
                marker = response.get('NextMarker', '')
            else:
                break

        logger.info(f"✅ COS: 加载了 {len(existing_files)} 个音频文件（{page_count} 页）")
        return existing_files

    except ImportError:
        logger.warning("qcloud_cos 未安装，无法检查 COS")
        return set()
    except Exception as e:
        logger.error(f"从 COS 获取文件列表失败: {e}")
        return set()


async def get_all_audio_files_from_cos() -> set:
    """
    从 COS 获取所有音频文件列表（异步包装器）

    Returns:
        包含所有文件名（不含路径和扩展名）的 Set
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_cos_files_sync)


async def check_all_sentences(
    sentences: List[Dict[str, Any]],
    max_concurrent_checks: int = 4
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    检查所有句子的音频文件是否存在（批量优化版本）

    Args:
        sentences: 句子列表
        max_concurrent_checks: 参数保留但不使用（批量检查不需要并发控制）

    Returns:
        (all_results, missing_sentences) 元组
        - all_results: 所有句子的检查结果
        - missing_sentences: 缺失音频的句子列表
    """
    logger.info(f"开始检查 {len(sentences)} 个句子的音频文件...")
    start_time = time.time()

    # 步骤1: 批量获取 R2 和 COS 的所有文件列表
    logger.info("📥 正在从 R2 和 COS 批量获取文件列表...")
    r2_files, cos_files = await asyncio.gather(
        get_all_audio_files_from_r2(),
        get_all_audio_files_from_cos()
    )

    logger.info(f"   R2 文件数: {len(r2_files)}")
    logger.info(f"   COS 文件数: {len(cos_files)}")

    # 步骤2: 检查每个句子
    all_results = []
    missing_audio_sentences = []

    logger.info("🔍 开始检查句子音频状态...")
    for idx, sentence in enumerate(sentences):
        en = sentence.get('en', '').strip()
        if not en:
            continue

        # 生成哈希
        sentence_hash = generate_sentence_hash(en)

        # 在 Set 中快速查找
        r2_exists = sentence_hash in r2_files
        cos_exists = sentence_hash in cos_files

        # 创建结果对象
        result = sentence.copy()
        result['sentence_hash'] = sentence_hash
        result['r2_exists'] = r2_exists
        result['cos_exists'] = cos_exists
        result['audio_exists'] = r2_exists and cos_exists

        all_results.append(result)

        # 如果任一存储不存在，则需要生成
        if not result['audio_exists']:
            missing_audio_sentences.append(result)

        # 进度显示（每100个或最后一个）
        if (idx + 1) % 100 == 0 or (idx + 1) == len(sentences):
            logger.info(
                f"检查进度: {idx + 1}/{len(sentences)} "
                f"({(idx + 1) * 100 / len(sentences):.1f}%)"
            )

    total_time = time.time() - start_time
    logger.info(f"✅ 检查完成！总耗时: {total_time:.1f}秒")
    logger.info(f"   - 检查句子数: {len(all_results)}")
    logger.info(f"   - 音频已存在: {len(all_results) - len(missing_audio_sentences)}")
    logger.info(f"   - 音频缺失: {len(missing_audio_sentences)}")

    return all_results, missing_audio_sentences


async def generate_and_upload_audio(
    sentences: List[Dict[str, Any]],
    max_concurrent_audio: int = 8,
    max_concurrent_r2: int = 20,
    max_workers_cos: int = 8
) -> Dict[str, Any]:
    """
    生成并上传音频文件（优化：先检查本地文件，有则直接上传）

    Args:
        sentences: 需要生成音频的句子列表
        max_concurrent_audio: 音频生成最大并发数（默认：8）
        max_concurrent_r2: R2 上传最大并发数（默认：20）
        max_workers_cos: COS 上传最大线程数（默认：8）

    Returns:
        统计结果
    """
    if not sentences:
        logger.info("没有需要生成的音频文件")
        return {
            'total': 0,
            'generated': 0,
            'uploaded_r2': 0,
            'uploaded_cos': 0
        }

    from utils.audio_generator import generate_batch_audio, check_edge_tts_available
    from services.storage_service import upload_audio_files

    # 检查 edge-tts 是否可用
    if not check_edge_tts_available():
        raise Exception("edge-tts 未安装，请先安装: pip install edge-tts")

    # 创建音频目录
    audio_dir = Path("audio/sentences")
    audio_dir.mkdir(parents=True, exist_ok=True)

    # 步骤1: 检查本地文件是否已存在
    logger.info(f"🔍 检查本地 audio/sentences/ 文件夹...")
    local_files = []
    need_generate = []

    for sentence in sentences:
        en = sentence.get('en', '').strip()
        if not en:
            continue

        sentence_hash = generate_sentence_hash(en)
        audio_path = audio_dir / f"{sentence_hash}.mp3"

        if audio_path.exists() and audio_path.stat().st_size > 0:
            # 本地文件存在，直接加入上传列表
            local_files.append({
                'en': en,
                'sentence_hash': sentence_hash,
                'audio_path': str(audio_path)
            })
        else:
            # 需要生成
            need_generate.append(en)

    logger.info(f"   ✅ 本地已存在: {len(local_files)} 个文件")
    logger.info(f"   🎵 需要生成: {len(need_generate)} 个文件")

    # 步骤2: 生成缺失的音频文件
    audio_gen_time = 0
    newly_generated = []
    processed_sentences = []  # 初始化，避免UnboundLocalError

    if need_generate:
        logger.info(f"开始生成 {len(need_generate)} 个音频文件（并发数：{max_concurrent_audio}）...")
        audio_gen_start = time.time()

        # 生成音频文件
        processed_sentences = await generate_batch_audio(
            sentences=need_generate,
            audio_dir=audio_dir,
            voice="en-US-AvaMultilingualNeural",
            max_concurrent=max_concurrent_audio,
            timeout_per_sentence=30
        )

        audio_gen_time = time.time() - audio_gen_start

        # 统计新生成的文件
        newly_generated = [p for p in processed_sentences if p.get('audio_generated') and not p.get('existed')]

        logger.info(f"✅ 音频生成完成，耗时: {audio_gen_time:.1f}秒")
        logger.info(f"   - 新生成: {len(newly_generated)} 个文件")
        logger.info(f"   - 生成速度: {len(need_generate) / audio_gen_time:.2f} 句/秒")

        # 将新生成的文件添加到本地文件列表
        for processed in processed_sentences:
            if processed.get('audio_generated') and processed.get('audio_path'):
                local_files.append({
                    'en': processed.get('en', ''),
                    'sentence_hash': processed['sentence_hash'],
                    'audio_path': processed['audio_path']
                })
    else:
        logger.info("✅ 所有文件都已在本地存在，无需生成")

    # 步骤3: 准备上传文件列表（根据缺失情况分别上传）
    # 为每个句子匹配原始检查结果，确定需要上传到哪个存储
    upload_files_r2 = []
    upload_files_cos = []

    # 创建句子hash到检查结果的映射
    sentence_check_map = {s.get('sentence_hash'): s for s in sentences}

    for file_info in local_files:
        audio_path = file_info['audio_path']
        sentence_hash = file_info['sentence_hash']

        if Path(audio_path).exists():
            object_key = f"audio/sentences/{sentence_hash}.mp3"
            file_data = {
                'file_path': audio_path,
                'object_key': object_key,
                'sentence_hash': sentence_hash
            }

            # 获取原始检查结果
            check_result = sentence_check_map.get(sentence_hash, {})
            r2_exists = check_result.get('r2_exists', False)
            cos_exists = check_result.get('cos_exists', False)

            # 只上传到缺失的存储
            if not r2_exists:
                upload_files_r2.append(file_data)
            if not cos_exists:
                upload_files_cos.append(file_data)

    logger.info(f"准备上传文件:")
    logger.info(f"   - R2 需要上传: {len(upload_files_r2)} 个")
    logger.info(f"   - COS 需要上传: {len(upload_files_cos)} 个")

    upload_start = time.time()

    # 分别上传到 R2 和 COS（根据缺失情况）
    if upload_files_r2 or upload_files_cos:
        cos_results, r2_results, cos_stats, r2_stats = await upload_audio_files(
            upload_files=[],  # 使用 r2_files 和 cos_files 指定各自的上传列表
            upload_to_cos=len(upload_files_cos) > 0,
            upload_to_r2=len(upload_files_r2) > 0,
            max_concurrent_r2=max_concurrent_r2,
            max_workers_cos=max_workers_cos,
            r2_files=upload_files_r2,  # 只上传到 R2 缺失的文件
            cos_files=upload_files_cos  # 只上传到 COS 缺失的文件
        )
    else:
        logger.info("所有文件都已在R2和COS存在，无需上传")
        cos_results, r2_results = [], []
        cos_stats = {'total_uploads': 0, 'successful_uploads': 0, 'failed_uploads': 0}
        r2_stats = {'total_uploads': 0, 'successful_uploads': 0, 'failed_uploads': 0}

    upload_time = time.time() - upload_start
    logger.info(f"✅ 上传完成，耗时: {upload_time:.1f}秒")

    total_time = audio_gen_time + upload_time

    stats = {
        'total': len(sentences),
        'generated': len(newly_generated),  # 使用newly_generated，更准确
        'local_existed': len(local_files) - len(newly_generated),  # 本地已存在的数量
        'uploaded_r2': r2_stats.get('successful_uploads', 0),
        'uploaded_cos': cos_stats.get('successful_uploads', 0),
        'r2_stats': r2_stats,
        'cos_stats': cos_stats,
        'performance': {
            'audio_generation_time': audio_gen_time,
            'upload_time': upload_time,
            'total_time': total_time,
            'audio_gen_rate': len(need_generate) / audio_gen_time if audio_gen_time > 0 else 0,
            'upload_rate': len(upload_files) / upload_time if upload_time > 0 else 0
        }
    }

    logger.info("=" * 60)
    logger.info("完成统计：")
    logger.info(f"  - 总句子数: {stats['total']}")
    logger.info(f"  - 本地已存在: {stats['local_existed']}")
    logger.info(f"  - 新生成: {stats['generated']}")
    logger.info(f"  - R2 上传成功: {stats['uploaded_r2']}")
    logger.info(f"  - COS 上传成功: {stats['uploaded_cos']}")
    logger.info("")
    logger.info("性能统计：")
    if audio_gen_time > 0:
        logger.info(f"  - 音频生成耗时: {audio_gen_time:.1f}秒 ({stats['performance']['audio_gen_rate']:.2f} 句/秒)")
    logger.info(f"  - 上传耗时: {upload_time:.1f}秒 ({stats['performance']['upload_rate']:.2f} 文件/秒)")
    logger.info(f"  - 总耗时: {total_time:.1f}秒")
    logger.info("=" * 60)

    return stats


def group_by_episode(sentences: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    """
    按 episode ID 分组句子

    Args:
        sentences: 句子列表

    Returns:
        按 episode_id 分组的字典
    """
    episodes = {}
    for sentence in sentences:
        episode_id = sentence.get('episode_id')
        if episode_id not in episodes:
            episodes[episode_id] = []
        episodes[episode_id].append(sentence)

    return episodes


def format_check_results(all_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    格式化检查结果，按 episode 分组

    Args:
        all_results: 所有句子的检查结果

    Returns:
        格式化后的结果字典
    """
    # 按 episode 分组
    episodes = group_by_episode(all_results)

    # 构建结果
    formatted_results = {
        'total_sentences': len(all_results),
        'total_episodes': len(episodes),
        'episodes': {}
    }

    for episode_id in sorted(episodes.keys()):
        episode_sentences = episodes[episode_id]

        # 统计该 episode 的音频状态
        audio_exists_count = sum(1 for s in episode_sentences if s.get('audio_exists', False))
        r2_exists_count = sum(1 for s in episode_sentences if s.get('r2_exists', False))
        cos_exists_count = sum(1 for s in episode_sentences if s.get('cos_exists', False))

        formatted_results['episodes'][f'EP{episode_id}'] = {
            'episode_id': episode_id,
            'total_sentences': len(episode_sentences),
            'audio_exists_count': audio_exists_count,
            'audio_missing_count': len(episode_sentences) - audio_exists_count,
            'r2_exists_count': r2_exists_count,
            'cos_exists_count': cos_exists_count,
            'sentences': [
                {
                    'sentence_id': s.get('sentence_id'),
                    'episode_sequence': s.get('episode_sequence'),
                    'en': s.get('en'),
                    'sentence_hash': s.get('sentence_hash'),
                    'r2_exists': s.get('r2_exists', False),
                    'cos_exists': s.get('cos_exists', False),
                    'audio_exists': s.get('audio_exists', False)
                }
                for s in sorted(episode_sentences, key=lambda x: x.get('episode_sequence', 0))
            ]
        }

    return formatted_results


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='检查并生成指定 Episode 范围的音频文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  %(prog)s -s 238 -e 300                    # 处理 Episode 238-300
  %(prog)s --start 1 --end 100               # 处理 Episode 1-100
  %(prog)s -s 50 -e 60 --checks 100          # 自定义检查并发数
  %(prog)s -s 1 -e 10 --audio-workers 10     # 自定义音频生成并发数

性能参数:
  默认配置已针对一般场景优化，通常无需修改
  如需调优，可根据服务器性能和网络情况调整各项并发参数
        """
    )

    # 必需参数
    parser.add_argument(
        '-s', '--start',
        type=int,
        required=True,
        help='起始 Episode ID（必需）'
    )

    parser.add_argument(
        '-e', '--end',
        type=int,
        required=True,
        help='结束 Episode ID（必需）'
    )

    # 可选的性能参数
    parser.add_argument(
        '--checks',
        type=int,
        default=4,
        help='文件检查并发数（默认：4）'
    )

    parser.add_argument(
        '--audio-workers',
        type=int,
        default=3,
        help='音频生成并发数（默认：3）'
    )

    parser.add_argument(
        '--r2-workers',
        type=int,
        default=2,
        help='R2 上传并发数（默认：2）'
    )

    parser.add_argument(
        '--cos-workers',
        type=int,
        default=3,
        help='COS 上传线程数（默认：3）'
    )

    parser.add_argument(
        '--data-file',
        type=str,
        default='prod_lingohow-sentences-20251113.json',
        help='输入数据文件路径（默认：prod_lingohow-sentences-20251113.json）'
    )

    args = parser.parse_args()

    # 验证参数
    if args.start < 1:
        parser.error("起始 Episode ID 必须大于等于 1")

    if args.end < args.start:
        parser.error(f"结束 Episode ID ({args.end}) 不能小于起始 Episode ID ({args.start})")

    return args


async def main():
    """主函数"""
    # 解析命令行参数
    args = parse_arguments()

    # 从参数获取配置
    START_EPISODE = args.start
    END_EPISODE = args.end
    MAX_CONCURRENT_CHECKS = args.checks
    MAX_CONCURRENT_AUDIO = args.audio_workers
    MAX_CONCURRENT_R2 = args.r2_workers
    MAX_WORKERS_COS = args.cos_workers
    data_file_path = args.data_file

    # 读取数据文件
    data_file = Path(data_file_path)

    if not data_file.exists():
        logger.error(f"数据文件不存在: {data_file}")
        return

    logger.info("=" * 60)
    logger.info(f"📖 读取数据文件: {data_file}")
    with open(data_file, 'r', encoding='utf-8') as f:
        all_sentences = json.load(f)

    logger.info(f"   总句子数: {len(all_sentences)}")

    # 筛选指定范围的 episode 句子
    filtered_sentences = [
        s for s in all_sentences
        if START_EPISODE <= s.get('episode_id', 0) <= END_EPISODE
    ]

    logger.info(f"   筛选范围: Episode {START_EPISODE} 到 Episode {END_EPISODE}")
    logger.info(f"   筛选后句子数: {len(filtered_sentences)}")

    logger.info("")
    logger.info("⚙️  性能配置:")
    logger.info(f"   - 文件检查并发数: {MAX_CONCURRENT_CHECKS}")
    logger.info(f"   - 音频生成并发数: {MAX_CONCURRENT_AUDIO}")
    logger.info(f"   - R2 上传并发数: {MAX_CONCURRENT_R2}")
    logger.info(f"   - COS 上传线程数: {MAX_WORKERS_COS}")
    logger.info("=" * 60)

    # 检查音频文件是否存在
    all_results, missing_sentences = await check_all_sentences(
        filtered_sentences,
        max_concurrent_checks=MAX_CONCURRENT_CHECKS
    )

    # 格式化并保存完整的检查结果（按 episode 分组）
    formatted_results = format_check_results(all_results)

    # 保存完整检查结果
    full_results_file = Path(
        f"audio_check_results_ep{START_EPISODE}-{END_EPISODE}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(full_results_file, 'w', encoding='utf-8') as f:
        json.dump(formatted_results, f, ensure_ascii=False, indent=2)

    logger.info(f"📊 完整检查结果已保存到: {full_results_file}")

    # 同时保存缺失音频的句子列表（用于生成）
    if missing_sentences:
        missing_file = Path(
            f"missing_audio_ep{START_EPISODE}-{END_EPISODE}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(missing_file, 'w', encoding='utf-8') as f:
            json.dump(missing_sentences, f, ensure_ascii=False, indent=2)

        logger.info(f"💾 缺失音频的句子已保存到: {missing_file}")

    # 打印详细统计信息
    logger.info("")
    logger.info("=" * 60)
    logger.info("📊 检查结果统计")
    logger.info("=" * 60)

    # 总体统计
    total_sentences = len(all_results)
    audio_exists = total_sentences - len(missing_sentences)

    logger.info(f"总句子数: {total_sentences}")
    logger.info(f"  - 音频已存在: {audio_exists} ({audio_exists * 100 / total_sentences:.1f}%)")
    logger.info(f"  - 音频缺失: {len(missing_sentences)} ({len(missing_sentences) * 100 / total_sentences:.1f}%)")

    # 缺失详情
    if missing_sentences:
        r2_missing = sum(1 for s in missing_sentences if not s.get('r2_exists', False))
        cos_missing = sum(1 for s in missing_sentences if not s.get('cos_exists', False))
        both_missing = sum(1 for s in missing_sentences if not s.get('r2_exists', False) and not s.get('cos_exists', False))

        logger.info(f"\n缺失详情:")
        logger.info(f"  - R2 缺失: {r2_missing}")
        logger.info(f"  - COS 缺失: {cos_missing}")
        logger.info(f"  - 两者都缺失: {both_missing}")

        # 按 episode 显示缺失统计
        missing_by_episode = group_by_episode(missing_sentences)
        logger.info(f"\n按 Episode 分布:")
        for episode_id in sorted(missing_by_episode.keys()):
            count = len(missing_by_episode[episode_id])
            logger.info(f"  - EP{episode_id}: {count} 个句子缺失音频")

    logger.info("=" * 60)

    # 询问是否生成音频
    if missing_sentences:
        logger.info("")
        logger.info("=" * 60)
        logger.info("🎵 是否继续生成并上传缺失的音频文件？")
        logger.info(f"   将生成 {len(missing_sentences)} 个音频文件")
        logger.info(f"   范围: Episode {START_EPISODE} 到 Episode {END_EPISODE}")
        logger.info("   按 Ctrl+C 取消，或等待 10 秒自动继续...")
        logger.info("=" * 60)

        try:
            await asyncio.sleep(10)
        except KeyboardInterrupt:
            logger.info("用户取消操作")
            return

        # 生成并上传音频
        stats = await generate_and_upload_audio(
            missing_sentences,
            max_concurrent_audio=MAX_CONCURRENT_AUDIO,
            max_concurrent_r2=MAX_CONCURRENT_R2,
            max_workers_cos=MAX_WORKERS_COS
        )

        # 保存统计结果
        stats_file = Path(
            f"audio_stats_ep{START_EPISODE}-{END_EPISODE}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        # 添加范围信息到统计
        stats['episode_range'] = {
            'start': START_EPISODE,
            'end': END_EPISODE,
            'total_episodes': END_EPISODE - START_EPISODE + 1
        }

        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

        logger.info(f"📊 统计结果已保存到: {stats_file}")
        logger.info(f"✅ 所有操作完成！(Episode {START_EPISODE}-{END_EPISODE})")
    else:
        logger.info(f"✅ Episode {START_EPISODE}-{END_EPISODE} 的所有句子音频文件都已存在，无需生成！")


if __name__ == "__main__":
    asyncio.run(main())
