# 音频检查和生成脚本使用指南

## 脚本功能

`check_and_generate_audio.py` - 检查并生成指定 Episode 范围的音频文件

## 基本用法

### 必需参数

```bash
python check_and_generate_audio.py -s <起始episode> -e <结束episode>
```

或使用完整参数名：

```bash
python check_and_generate_audio.py --start <起始episode> --end <结束episode>
```

### 使用示例

#### 示例 1: 处理 Episode 238-300

```bash
python check_and_generate_audio.py -s 238 -e 300
```

#### 示例 2: 处理 Episode 1-100

```bash
python check_and_generate_audio.py --start 1 --end 100
```

#### 示例 3: 处理单个 Episode

```bash
python check_and_generate_audio.py -s 50 -e 50
```

#### 示例 4: 处理 Episode 261-300

```bash
python check_and_generate_audio.py -s 261 -e 300
```

## 高级选项

### 自定义性能参数

如果需要调整并发数以优化性能：

```bash
python check_and_generate_audio.py -s 1 -e 100 \
  --checks 100 \
  --audio-workers 10 \
  --r2-workers 30 \
  --cos-workers 12
```

### 使用自定义数据文件

```bash
python check_and_generate_audio.py -s 1 -e 50 \
  --data-file /path/to/your/data.json
```

## 完整参数列表

### 必需参数

| 参数 | 简写 | 类型 | 说明 |
|------|------|------|------|
| `--start` | `-s` | int | 起始 Episode ID（必需） |
| `--end` | `-e` | int | 结束 Episode ID（必需） |

### 可选参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--checks` | 50 | 文件检查并发数 |
| `--audio-workers` | 8 | 音频生成并发数 |
| `--r2-workers` | 20 | R2 上传并发数 |
| `--cos-workers` | 8 | COS 上传线程数 |
| `--data-file` | prod_lingohow-sentences-20251113.json | 输入数据文件路径 |

## 输出文件

### 缺失音频列表

格式：`missing_audio_ep<start>-<end>_<timestamp>.json`

示例：
```
missing_audio_ep238-300_20251119_143022.json
```

包含所有缺失音频文件的句子数据。

### 统计结果

格式：`audio_stats_ep<start>-<end>_<timestamp>.json`

示例：
```
audio_stats_ep238-300_20251119_143522.json
```

包含详细的性能统计和上传结果，新增字段：

```json
{
  "episode_range": {
    "start": 238,
    "end": 300,
    "total_episodes": 63
  },
  "total": 1500,
  "generated": 1495,
  "uploaded_r2": 1495,
  "uploaded_cos": 1495,
  "performance": {
    "audio_generation_time": 187.3,
    "upload_time": 74.8,
    "total_time": 262.1,
    "audio_gen_rate": 7.98,
    "upload_rate": 19.98
  }
}
```

## 工作流程

1. **读取数据**
   - 从指定的 JSON 文件读取所有句子
   - 显示总句子数

2. **筛选范围**
   - 根据 `-s` 和 `-e` 参数筛选指定范围的 episode
   - 显示筛选后的句子数量

3. **检查存在性**
   - 并发检查每个句子的音频是否存在于 R2 和 COS
   - 显示实时进度和速度

4. **保存缺失列表**
   - 将缺失音频的句子保存到 JSON 文件
   - 显示统计信息（R2 缺失、COS 缺失、两者都缺失）

5. **确认生成**
   - 等待 10 秒确认（或按 Ctrl+C 取消）

6. **生成音频**
   - 使用 edge-tts 并发生成音频文件
   - 显示生成进度和速度

7. **上传云存储**
   - 同时上传到 R2 和 COS
   - 显示上传进度和结果

8. **保存统计**
   - 保存详细的性能统计和结果

## 性能调优指南

### 根据网络环境调整

#### 低网速环境 (< 10Mbps)
```bash
python check_and_generate_audio.py -s 1 -e 100 \
  --checks 30 \
  --audio-workers 5 \
  --r2-workers 10 \
  --cos-workers 4
```

#### 中等网速环境 (10-50Mbps)
```bash
python check_and_generate_audio.py -s 1 -e 100 \
  --checks 50 \
  --audio-workers 8 \
  --r2-workers 20 \
  --cos-workers 8
```

#### 高网速环境 (> 50Mbps)
```bash
python check_and_generate_audio.py -s 1 -e 100 \
  --checks 100 \
  --audio-workers 10 \
  --r2-workers 30 \
  --cos-workers 12
```

### 根据服务器配置调整

#### 2核 2GB
```bash
python check_and_generate_audio.py -s 1 -e 100 \
  --checks 30 \
  --audio-workers 4 \
  --r2-workers 10 \
  --cos-workers 4
```

#### 4核 4GB
```bash
python check_and_generate_audio.py -s 1 -e 100 \
  --checks 50 \
  --audio-workers 8 \
  --r2-workers 20 \
  --cos-workers 8
```

#### 8核+ 8GB+
```bash
python check_and_generate_audio.py -s 1 -e 100 \
  --checks 100 \
  --audio-workers 12 \
  --r2-workers 40 \
  --cos-workers 16
```

## 常见场景

### 场景 1: 处理新导入的 Episodes

```bash
# 假设新导入了 Episode 301-350
python check_and_generate_audio.py -s 301 -e 350
```

### 场景 2: 重新检查特定范围

```bash
# 检查并修复 Episode 100-200
python check_and_generate_audio.py -s 100 -e 200
```

### 场景 3: 批量处理（分段执行）

```bash
# 分段处理大范围，避免一次性处理过多
python check_and_generate_audio.py -s 1 -e 50
python check_and_generate_audio.py -s 51 -e 100
python check_and_generate_audio.py -s 101 -e 150
```

### 场景 4: 快速测试

```bash
# 处理少量 episodes 进行测试
python check_and_generate_audio.py -s 1 -e 5
```

## 帮助信息

查看完整的帮助信息：

```bash
python check_and_generate_audio.py --help
```

输出：

```
usage: check_and_generate_audio.py [-h] -s START -e END [--checks CHECKS]
                                   [--audio-workers AUDIO_WORKERS]
                                   [--r2-workers R2_WORKERS]
                                   [--cos-workers COS_WORKERS]
                                   [--data-file DATA_FILE]

检查并生成指定 Episode 范围的音频文件

options:
  -h, --help            show this help message and exit
  -s START, --start START
                        起始 Episode ID（必需）
  -e END, --end END     结束 Episode ID（必需）
  --checks CHECKS       文件检查并发数（默认：50）
  --audio-workers AUDIO_WORKERS
                        音频生成并发数（默认：8）
  --r2-workers R2_WORKERS
                        R2 上传并发数（默认：20）
  --cos-workers COS_WORKERS
                        COS 上传线程数（默认：8）
  --data-file DATA_FILE
                        输入数据文件路径（默认：prod_lingohow-sentences-20251113.json）

示例用法:
  check_and_generate_audio.py -s 238 -e 300                    # 处理 Episode 238-300
  check_and_generate_audio.py --start 1 --end 100               # 处理 Episode 1-100
  check_and_generate_audio.py -s 50 -e 60 --checks 100          # 自定义检查并发数
  check_and_generate_audio.py -s 1 -e 10 --audio-workers 10     # 自定义音频生成并发数

性能参数:
  默认配置已针对一般场景优化，通常无需修改
  如需调优，可根据服务器性能和网络情况调整各项并发参数
```

## 错误处理

### 参数验证

脚本会自动验证参数的有效性：

```bash
# 错误：起始 ID < 1
python check_and_generate_audio.py -s 0 -e 100
# 输出：error: 起始 Episode ID 必须大于等于 1

# 错误：结束 ID < 起始 ID
python check_and_generate_audio.py -s 100 -e 50
# 输出：error: 结束 Episode ID (50) 不能小于起始 Episode ID (100)
```

### 数据文件不存在

```bash
python check_and_generate_audio.py -s 1 -e 10 --data-file missing.json
# 输出：数据文件不存在: missing.json
```

## 日志输出示例

```
============================================================
📖 读取数据文件: prod_lingohow-sentences-20251113.json
   总句子数: 45678
   筛选范围: Episode 238 到 Episode 300
   筛选后句子数: 2156

⚙️  性能配置:
   - 文件检查并发数: 50
   - 音频生成并发数: 8
   - R2 上传并发数: 20
   - COS 上传线程数: 8
============================================================
开始检查 2156 个句子的音频文件（并发数：50）...
检查进度: 500/2156 (23.2%) - 速度: 42.3 句/秒 - 预计剩余: 39秒
检查进度: 1000/2156 (46.4%) - 速度: 43.1 句/秒 - 预计剩余: 27秒
检查进度: 1500/2156 (69.6%) - 速度: 44.2 句/秒 - 预计剩余: 15秒
检查进度: 2000/2156 (92.8%) - 速度: 44.8 句/秒 - 预计剩余: 3秒
检查进度: 2156/2156 (100.0%) - 速度: 45.1 句/秒 - 预计剩余: 0秒
✅ 检查完成！总耗时: 47.8秒
   - 检查句子数: 2156
   - 缺失音频: 150
   - 平均速度: 45.1 句/秒

💾 缺失音频的句子已保存到: missing_audio_ep238-300_20251119_143022.json

缺失统计：
    - 总缺失: 150
    - R2 缺失: 120
    - COS 缺失: 80
    - 两者都缺失: 50

============================================================
🎵 是否继续生成并上传缺失的音频文件？
   将生成 150 个音频文件
   范围: Episode 238 到 Episode 300
   按 Ctrl+C 取消，或等待 10 秒自动继续...
============================================================
...
```

## 注意事项

1. **Episode ID 必须存在** - 确保指定范围内的 episodes 在数据文件中存在
2. **网络稳定性** - 建议在网络稳定的环境下运行
3. **磁盘空间** - 确保有足够的磁盘空间存储生成的音频文件
4. **并发限制** - 过高的并发可能导致 API 限流，建议使用默认值
5. **中断恢复** - 如果中途中断，可以重新运行相同的命令，已存在的文件会自动跳过

## 相关文档

- [性能优化说明](performance_optimization.md)
- [Phrase Audio API 使用指南](phrase_audio_api_usage.md)
