# LTX Director Motion Brush 日本語ガイド

LTX Director Motion Brush は、ComfyUI 上で LTX 2.3 のタイムライン生成、画像ごとの Motion Brush、Retake Mode、Motion Carry を扱うためのカスタムノードパックです。

このリポジトリは日本語ユーザー向けの導入ガイドと日本語メモ付きワークフローを含みます。現時点ではノード本体の UI は主に英語ですが、必要なモデル、導入手順、基本的な使い方、よくある調整ポイントを日本語で確認できます。

## 概要

- 画像タイムライン上で、各画像に直接 Motion Brush の軌跡を描けます。
- 描いた軌跡を LTX 2.3 IC-LoRA Motion-Track-Control 用のガイド動画に変換します。
- 画像ガイドと Motion IC-LoRA の強さを調整するための Guide Attention ノードを含みます。
- Retake Mode、Motion Carry、Matte、画像ごとの Guide Strength に対応しています。
- アップロード先やノード名は upstream の LTX Director v2 と衝突しないように分離されています。

## インストール

Comfy Registry / ComfyUI-Manager から利用できる場合は、次のコマンドでインストールできます。

```powershell
comfy node install ltx-director-motion-brush
```

手動で入れる場合は、ComfyUI の `custom_nodes` フォルダにこのリポジトリを clone してください。

```powershell
cd C:\ComfyUI\app\custom_nodes
git clone https://github.com/exportAnything/ComfyUI-LTX-Director-Motion-Brush.git
```

インストールまたは更新後は ComfyUI を再起動してください。

## 必要なカスタムノード

このワークフローでは、次のカスタムノードも別途インストールまたは更新してください。

- `ComfyUI-LTXVideo`
- `comfyui-kjnodes`
- `ComfyUI-Impact-Pack`

GGUF 低 VRAM ワークフローを使う場合は、次も追加でインストールしてください。

- `ComfyUI-GGUF`

また、ワークフロー内には ComfyUI core の動画ノードや、保存済みの grouped/subgraph ノードも含まれています。

## 必要なモデル

このリポジトリにモデルファイルは同梱されていません。LTXVideo のワークフローで使う場所に、各モデルを配置してください。

一般的には次の LTX 2.3 関連アセットが必要です。

- LTX 2.3 の checkpoint または UNet 構成
- LTX 2.3 の text encoder
- LTX 2.3 の VAE または tiny VAE
- LTX 2.3 の latent upscale model
- Lightricks IC-LoRA Ingredients for LTX 2.3: https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Ingredients
- Lightricks IC-LoRA Motion-Track-Control for LTX 2.3: https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Motion-Track-Control

Motion Brush には、Motion-Track-Control 側の LoRA が必要です。例:

```text
ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors
```

## ワークフロー

推奨の低 VRAM ワークフロー:

```text
example_workflows/LTX_Director_Motion_Brush_V2_Low_Vram.json
```

非常に低い VRAM 向けの GGUF ワークフロー:

```text
example_workflows/LTX_Director_Motion_Brush_V2_Low_Vram_GGUF.json
```

GGUF 版は GGUF 用の UNet/CLIP loader を使うため、`ComfyUI-GGUF` と対応する GGUF model file が必要です。

英語版の標準ワークフロー:

```text
example_workflows/LTX_Director_Motion_Brush_V2.json
```

日本語メモ付きワークフロー:

```text
example_workflows/LTX_Director_Motion_Brush_V2_ja.json
```

日本語版は、ワークフロー内の説明メモや一部タイトルを日本語にしたコピーです。ノード本体の挙動やクラス名は変更していません。

低 VRAM / GGUF ワークフローには、`ComfyUI/input/exportanything` 配下のサンプル入力を参照するタイムラインが含まれる場合があります。読み込み後に画像や音声が見つからない場合は、自分の入力メディアに置き換えてください。

## 基本的な使い方

1. 必要なカスタムノードとモデルをインストールします。
2. ComfyUI を再起動します。
3. まず `example_workflows/LTX_Director_Motion_Brush_V2_Low_Vram.json` を読み込みます。GGUF 環境では `example_workflows/LTX_Director_Motion_Brush_V2_Low_Vram_GGUF.json` を使います。
4. `LTX Director Motion Brush V2` ノードのタイムラインに画像を追加します。
5. `Motion Brush` をオンにして、動かしたい方向に軌跡を描きます。
6. 必要に応じて `Guide Strength`、`Carry Motion`、`Matte`、Retake Mode を調整します。
7. 生成結果が静的すぎる、または Motion Track の点に引っ張られすぎる場合は、Guide Attention や IC-LoRA guide strength を調整します。

## 重要な注意点

- Motion Brush の軌跡を編集する前に `Motion Brush` をオンにしてください。
- Motion Brush 有効時は、アスペクト比を守るため `resize_method` が `maintain aspect ratio` に固定されます。
- `Guide Strength` はタイムライン内の各画像ごとに効きます。
- `Carry Motion` の初期値は `0` です。これは前後のシーンに動きが漏れにくい安全な設定です。
- `Carry Motion` を 16 以上にすると、ある画像の motion guide を次の画像へ意図的に持ち越せます。
- Retake Mode では、意味のある変更を行うために最低 6 秒の選択が必要です。
- `ic-lora-motion-track` と `LTX Director Motion Brush V2 Guide Attention` は、Motion Brush と Retake Mode の重要な部分です。基本的にはバイパスしないでください。

## 調整のヒント

出力が静的すぎる、画像に固定されすぎる、Motion Track の点が強く出すぎる場合は、次の順番で調整するのがおすすめです。

1. `LTX Director Motion Brush V2 Guide Attention` を下げる。
2. Motion Track の点が映像に強く乗りすぎる場合は、`LTXAddVideoICLoRAGuide` の strength を下げる。
3. `LTXICLoRALoaderModelOnly` の `strength_model` は、LoRA 自体を弱めたい場合以外は 1 付近を維持する。

`Carry Motion` はグローバル設定ではありません。必要な画像ごとに調整してください。

## トラブルシュート

ワークフローが読み込めない場合:

- 必要なカスタムノードが入っているか確認してください。
- `ComfyUI-LTXVideo`、`comfyui-kjnodes`、`ComfyUI-Impact-Pack` を更新してください。
- このノードパックを更新した後、ComfyUI を再起動してください。

モデルが見つからない場合:

- LTXVideo の通常の配置先にモデルを置いてください。
- Hugging Face から取得した IC-LoRA Ingredients と Motion-Track-Control の両方が揃っているか確認してください。
- ファイル名や保存場所が、ワークフロー内の loader ノードの設定と一致しているか確認してください。

Retake Mode が思ったように効かない場合:

- 選択範囲が 6 秒以上あるか確認してください。
- Retake 元動画と生成設定のフレーム数、解像度、モデル構成が合っているか確認してください。

## クレジット

オリジナルの LTX Director v2 のコンセプトと実装は WhatDreamsCost によるものです。

```text
https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI
```

Motion Brush パッケージングと LTX 2.3 motion-track integration は exportAnything によるものです。

詳細は `ATTRIBUTION.md` を参照してください。
