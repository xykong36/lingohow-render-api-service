# Phrase Audio Generation API 使用指南

## API Endpoint

```
POST /api/phrase/generate-audio
```

## 功能说明

这个 API endpoint 用于生成单个 phrase（短语/词组）的音频文件，并自动上传到 R2 和 COS 存储。

### 主要特性

1. **智能格式化** - 自动应用 phrase 特定的格式化规则
   - 缩略词自动添加空格（如 "S.P.F." → "S P F"）
   - 移除句点和省略号以获得更清晰的 TTS 输出
   - 保持原始 phrase 结构用于文件命名

2. **存在性检查** - 可选地检查音频文件是否已存在于 R2/COS
   - 避免重复生成
   - 节省 API 调用和存储空间

3. **自动上传** - 生成后自动上传到两个云存储
   - Cloudflare R2
   - 腾讯云 COS

4. **详细反馈** - 返回完整的操作状态信息

## 请求格式

### Request Body (JSON)

```json
{
  "phrase": "string",              // 必需：要生成音频的 phrase 文本
  "voice": "string",               // 可选：TTS 语音模型，默认 "en-US-AvaMultilingualNeural"
  "check_existing": boolean        // 可选：是否检查已存在的文件，默认 true
}
```

### 字段说明

- **phrase** (必需)
  - 类型：string
  - 说明：要生成音频的 phrase 文本
  - 示例：`"break the ice"`, `"S.P.F."`, `"What's up?"`

- **voice** (可选)
  - 类型：string
  - 默认值：`"en-US-AvaMultilingualNeural"`
  - 说明：Edge TTS 语音模型
  - 其他选项：
    - `"en-US-JennyNeural"`
    - `"en-US-GuyNeural"`
    - `"en-GB-SoniaNeural"`
    - 等等...

- **check_existing** (可选)
  - 类型：boolean
  - 默认值：`true`
  - 说明：是否在生成前检查文件是否已存在于 R2/COS

## 响应格式

### Response Body (JSON)

```json
{
  "phrase": "string",              // 原始 phrase 文本
  "phrase_hash": "string",         // phrase 的哈希标识符
  "formatted_for_tts": "string",   // 格式化后的 TTS 文本
  "audio_generated": boolean,      // 是否生成了音频
  "audio_existed": boolean,        // 本地音频文件是否已存在
  "uploaded_r2": boolean,          // 是否成功上传到 R2
  "uploaded_cos": boolean,         // 是否成功上传到 COS
  "r2_existed": boolean,           // R2 中文件是否已存在
  "cos_existed": boolean,          // COS 中文件是否已存在
  "r2_object_key": "string",       // R2 对象键
  "cos_object_key": "string",      // COS 对象键
  "audio_file_path": "string",     // 本地音频文件路径
  "error": "string"                // 错误信息（如果有）
}
```

## 使用示例

### 示例 1: 生成普通 phrase 音频

```bash
curl -X POST "http://localhost:8000/api/phrase/generate-audio" \
  -H "Content-Type: application/json" \
  -d '{
    "phrase": "break the ice"
  }'
```

**响应示例：**

```json
{
  "phrase": "break the ice",
  "phrase_hash": "a1b2c3d4",
  "formatted_for_tts": "break the ice",
  "audio_generated": true,
  "audio_existed": false,
  "uploaded_r2": true,
  "uploaded_cos": true,
  "r2_existed": false,
  "cos_existed": false,
  "r2_object_key": "audio/expressionss/a1b2c3d4.mp3",
  "cos_object_key": "audio/expressionss/a1b2c3d4.mp3",
  "audio_file_path": "audio/expressionss/a1b2c3d4.mp3",
  "error": null
}
```

### 示例 2: 生成缩略词音频（自动格式化）

```bash
curl -X POST "http://localhost:8000/api/phrase/generate-audio" \
  -H "Content-Type: application/json" \
  -d '{
    "phrase": "S.P.F.",
    "voice": "en-US-JennyNeural"
  }'
```

**响应示例：**

```json
{
  "phrase": "S.P.F.",
  "phrase_hash": "e5f6g7h8",
  "formatted_for_tts": "S P F",
  "audio_generated": true,
  "audio_existed": false,
  "uploaded_r2": true,
  "uploaded_cos": true,
  "r2_existed": false,
  "cos_existed": false,
  "r2_object_key": "audio/expressionss/e5f6g7h8.mp3",
  "cos_object_key": "audio/expressionss/e5f6g7h8.mp3",
  "audio_file_path": "audio/expressionss/e5f6g7h8.mp3",
  "error": null
}
```

### 示例 3: 已存在的 phrase（跳过生成）

```bash
curl -X POST "http://localhost:8000/api/phrase/generate-audio" \
  -H "Content-Type: application/json" \
  -d '{
    "phrase": "break the ice",
    "check_existing": true
  }'
```

**响应示例（已存在）：**

```json
{
  "phrase": "break the ice",
  "phrase_hash": "a1b2c3d4",
  "formatted_for_tts": "break the ice",
  "audio_generated": false,
  "audio_existed": true,
  "uploaded_r2": false,
  "uploaded_cos": false,
  "r2_existed": true,
  "cos_existed": true,
  "r2_object_key": "audio/expressionss/a1b2c3d4.mp3",
  "cos_object_key": "audio/expressionss/a1b2c3d4.mp3",
  "audio_file_path": null,
  "error": null
}
```

### 示例 4: Python 客户端

```python
import requests

# API endpoint
url = "http://localhost:8000/api/phrase/generate-audio"

# 请求数据
payload = {
    "phrase": "What's up?",
    "voice": "en-US-AvaMultilingualNeural",
    "check_existing": True
}

# 发送请求
response = requests.post(url, json=payload)

# 处理响应
if response.status_code == 200:
    result = response.json()
    print(f"Phrase: {result['phrase']}")
    print(f"Hash: {result['phrase_hash']}")
    print(f"Formatted for TTS: {result['formatted_for_tts']}")
    print(f"Audio generated: {result['audio_generated']}")
    print(f"Uploaded to R2: {result['uploaded_r2']}")
    print(f"Uploaded to COS: {result['uploaded_cos']}")

    if result.get('error'):
        print(f"Error: {result['error']}")
else:
    print(f"Error: {response.status_code}")
    print(response.text)
```

### 示例 5: JavaScript/TypeScript 客户端

```typescript
interface PhraseAudioRequest {
  phrase: string;
  voice?: string;
  check_existing?: boolean;
}

interface PhraseAudioResponse {
  phrase: string;
  phrase_hash: string;
  formatted_for_tts: string;
  audio_generated: boolean;
  audio_existed: boolean;
  uploaded_r2: boolean;
  uploaded_cos: boolean;
  r2_existed: boolean;
  cos_existed: boolean;
  r2_object_key?: string;
  cos_object_key?: string;
  audio_file_path?: string;
  error?: string;
}

async function generatePhraseAudio(
  phrase: string,
  voice?: string
): Promise<PhraseAudioResponse> {
  const response = await fetch('http://localhost:8000/api/phrase/generate-audio', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      phrase,
      voice: voice || 'en-US-AvaMultilingualNeural',
      check_existing: true,
    }),
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return await response.json();
}

// 使用示例
(async () => {
  try {
    const result = await generatePhraseAudio("break the ice");
    console.log('Phrase audio generated:', result);
  } catch (error) {
    console.error('Error:', error);
  }
})();
```

## 特殊格式化规则

### 缩略词处理

当 phrase 是全大写字母时（如 "SPF"、"USA"），系统会自动在每个字母之间添加空格：

| 原始 Phrase | 格式化后 (TTS) | 说明 |
|------------|---------------|------|
| `"S.P.F."` | `"S P F"`     | 移除点号，添加空格 |
| `"USA"`    | `"U S A"`     | 每个字母单独发音 |
| `"I.D."`   | `"I D"`       | 缩略词格式化 |

### 混合内容处理

对于包含缩略词的混合内容，只对缩略词部分进行格式化：

| 原始 Phrase | 格式化后 (TTS) | 说明 |
|------------|---------------|------|
| `"Use SPF daily"` | `"Use S P F daily"` | 只格式化 "SPF" |
| `"What's up?"` | `"What's up?"` | 普通文本不变 |

## 错误处理

### 常见错误

#### 400 Bad Request - 空 phrase

```json
{
  "error": "Phrase text is required and cannot be empty",
  "detail": null
}
```

#### 500 Internal Server Error - Edge TTS 未安装

```json
{
  "error": "Edge TTS library is not installed. Please install edge-tts Python package.",
  "detail": null
}
```

#### 音频生成失败

```json
{
  "phrase": "test phrase",
  "phrase_hash": "xyz123",
  "formatted_for_tts": "test phrase",
  "audio_generated": false,
  "error": "Audio generation failed"
}
```

## 性能建议

1. **启用存在性检查** - 设置 `check_existing: true` 以避免重复生成
2. **批量处理** - 对于多个 phrases，考虑并发请求（但注意速率限制）
3. **缓存哈希** - 相同的 phrase 总是生成相同的哈希，可以用于缓存

## 文件存储位置

### 本地存储
- 路径：`audio/expressionss/{phrase_hash}.mp3`

### 云存储
- R2 路径：`audio/expressionss/{phrase_hash}.mp3`
- COS 路径：`audio/expressionss/{phrase_hash}.mp3`

## 相关 API

- `POST /api/sentence/generate-audio` - 批量生成句子音频
- `GET /` - 查看所有可用的 API endpoints
- `GET /health` - 健康检查

## 技术细节

### 哈希生成

Phrase 哈希基于清理后的文件名生成（移除标点、转小写），确保相同 phrase 的不同变体生成相同哈希：

```python
# "break the ice" -> "break_the_ice" -> MD5[:8]
# "break the ice!" -> "break_the_ice" -> MD5[:8] (相同哈希)
```

### TTS 引擎

- 使用 Microsoft Edge TTS
- 支持多种语音和语言
- 异步处理，超时时间 30 秒
- 自动重试机制（最多 2 次）
