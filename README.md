# Adobe Audition 多轨 SESX 自动拼接工具

按 txt 顺序将 `[编码] 标题.wav/flac` 音频拼接为 Adobe Audition `.sesx` 项目，支持中间音频插入、偶数分段、并行检测/转码。

## 安装

```powershell
pip install -r requirements.txt
```

Windows 下 `soundfile` 需要 libsndfile（通常随 wheel 提供）。使用 `--ignore-sample-rate` 时需安装 [ffmpeg](https://ffmpeg.org/) 并加入 PATH。

## 用法

**全部使用具名参数**：

```powershell
python main.py --audio-dir "D:\Songs" --order "D:\Songs\order.txt" --middle-code "0-0" --output "混音项目"
```

| 参数 | 说明 |
|------|------|
| `--audio-dir` | 源音频目录 |
| `--order` | 顺序 txt（每行一个编码，如 `101-1`） |
| `--middle-code` | 中间音频编码（如 `0-0`） |
| `--output` | 项目文件夹名（在 cwd 下创建） |
| `--ignore-sample-rate` | ffmpeg 统一转 FLAC 48kHz 24bit |
| `--segments` | 分段数（偶数 ≥2，默认不分段） |
| `--export-audio` | 导出 MP3（每段一个，320kbps；仅混该段轨道，等同静音其他轨） |

使用 `--export-audio` 需安装 [ffmpeg](https://ffmpeg.org/) 并加入 PATH。

### 输出结构

```
./混音项目/
├── 混音项目.sesx
├── 混音项目_1.mp3      # 仅 --export-audio 时
├── 混音项目_2.mp3
└── Sources/
    └── [编码] 标题.wav
```

### 文件名规则

- 格式：`[主编号-子编号] 标题.wav` 或 `.flac`
- 示例：`[101-1] 此刻Memories.wav`、`[32-1] [PJSK] Beyond the way.wav`

## 打包 exe

```powershell
pip install -r requirements-dev.txt
build.bat
```

产物：`dist/AutomaticAudioSplicing.exe`，CLI 参数与 Python 版相同。

## 架构

- **Facade**：`SplicingFacade` 统一编排
- **Strategy**：复制/转码、单段/分段布局
- **Builder**：`TimelineBuilder`、`SesxBuilder`

## 项目规格

- Session：48000 Hz / 24 bit / Stereo
- 拼接规则：`M → A1 → M → A2 → … → An`（双轨交替）
