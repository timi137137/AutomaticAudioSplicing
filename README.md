# Adobe Audition 多轨 SESX 自动拼接工具

按 txt 顺序将 `[编码] 标题.wav/flac` 音频拼接为 Adobe Audition `.sesx` 项目，支持中间音频插入、偶数分段、并行检测/转码。

## 安装

```powershell
pip install -r requirements.txt
```

Windows 下 `soundfile` 需要 libsndfile（通常随 wheel 提供）。使用 `--ignore-sample-rate` 或 `--excel` 模式时需安装 [ffmpeg](https://ffmpeg.org/) 并加入 PATH（`--excel` 另需 yt-dlp，已包含在 `requirements.txt`）。

## 用法

全部使用具名参数，两种输入模式二选一（`--order` 与 `--excel` 互斥）。

### 模式一：本地顺序文件

```powershell
python main.py --audio-dir "D:\Songs" --order "D:\Songs\order.txt" --middle-code "0-0" --output "混音项目"
```

### 模式二：Excel 下载排期

```powershell
python main.py --audio-dir "D:\Songs" --excel "D:\plan.xlsx" --middle-code "0-0" --output "混音项目"
```

Excel 首行表头缺一不可，数据按行从上到下作为拼接顺序：

| 列 | 说明 |
|----|------|
| 编码 | 作为 `[编码] 歌名.flac` 的编码 |
| 歌名 | 文件名与 Audition clip 显示名 |
| 时间区间 | `mm:ss - mm:ss`，必填；下载后按此区间裁剪 |
| 音源地址 | yt-dlp 支持的链接 |

流程：并行用 yt-dlp 下载音源 → 按区间裁剪 → loudnorm 两遍线性归一化（-16 LUFS / TP -1.5 dBTP，保留动态、不削峰）→ 产出 `downloads/[编码] 歌名.flac`（FLAC 48kHz/24bit）→ 交给拼接流程；`--audio-dir` 此时用于提供中间音频。

- `downloads/` 位于当前工作目录；已存在的有效产物会跳过下载。
- 某行失败不中断其它行；全部结束后若存在失败则报错退出，不生成项目。
- `--cookies` / `--proxy` 原样透传给 yt-dlp（仅 `--excel`）。

| 参数 | 说明 |
|------|------|
| `--audio-dir` | 本地音频目录（`--order` 时为源目录；`--excel` 时为中间音频所在目录） |
| `--order` | 顺序 txt（主编号如 `101` → 只用 `101-1`；完整码如 `101-2` → 按该文件） |
| `--excel` | 下载排期 Excel（列：编码 / 歌名 / 时间区间 / 音源地址） |
| `--middle-code` | 中间音频编码（如 `0-0`） |
| `--output` | 项目文件夹名（在 cwd 下创建） |
| `--cookies` / `--proxy` | yt-dlp 的 cookies 文件与代理（仅 `--excel`） |
| `--ignore-sample-rate` | ffmpeg 统一转 FLAC 48kHz 24bit |
| `--segments` | 分段数（偶数 ≥2，默认不分段） |
| `--export-audio` | 导出 MP3（每段一个，320kbps；仅混该段轨道，等同静音其他轨） |

`--excel` 模式需要 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 与 [ffmpeg](https://ffmpeg.org/) 加入 PATH；使用 `--export-audio` 亦需 ffmpeg。

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

代码位于根包 `aas`，依赖方向为 `domain` ← `service` ← `cli`；`infra` 依赖 `domain`，由 `service` 调用。

- `aas/domain/`：纯领域逻辑（`models`、`timeline` 时间轴构建与分段、`duration` 时长格式化、`schedule` 排期条目与区间解析），不涉及 I/O
- `aas/service.py`：`SplicingService` 编排完整流程（`--excel` 时先准备下载音源）
- `aas/infra/`：`scanner` 扫描探测、`processing` 复制/转码策略、`sesx` 项目生成、`packaging` 打包、`exporter` MP3 导出、`ffmpeg` 命令封装、`progress` 进度 UI、`resources` 资源定位；下载前置为 `sheet` 读表、`downloader` yt-dlp 并行下载、`normalize` 裁剪与 loudnorm 归一化
- `aas/cli.py`：命令行参数解析与结果输出；`main.py` 为入口

## 项目规格

- Session：48000 Hz / 24 bit / Stereo
- 拼接规则：`M → A1 → M → A2 → … → An`（双轨交替）
