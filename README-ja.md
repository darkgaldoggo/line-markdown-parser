# line-markdown-parser

LLMが生成したMarkdownを、LINEで読みやすいFlex Messageの辞書に変換するPythonライブラリです。実行時の外部依存はありません。

[English](README.md)

見出し、段落、リスト、引用、コードなどをチャットに適したレイアウトに変換し、長文を複数メッセージへ分割します。送信処理、認証情報、配送方法は利用するアプリケーションで管理します。

## インストール

Python 3.10以上が必要です。バージョン0.1.0は、現時点ではPyPIに未公開です。

ローカルのチェックアウトからインストールできます。

```bash
python -m pip install .
```

GitHubからバージョンを指定してインストールできます。

```bash
python -m pip install 'line-markdown-parser @ git+https://github.com/darkgaldragon/line-markdown-parser.git@v0.1.0'
```

## 使い方

```python
import json

from line_markdown_parser import convert_markdown_to_line_messages

markdown = """# プロジェクトの状況

**初稿**ができました。

- サンプルを確認する
- [ガイド](https://example.com/guide)を読む

| 項目 | 状況 |
| --- | --- |
| ドキュメント | 完了 |
| サンプル | 作成中 |
"""

messages = convert_markdown_to_line_messages(markdown)
print(json.dumps(messages, ensure_ascii=False, indent=2))
```

戻り値の各要素は、`type: "flex"`、`altText`、単一の `bubble` を持つ `contents` で構成されるメッセージオブジェクトです。利用するLINE API連携処理に、この辞書を渡してください。このライブラリはネットワーク通信を行わず、LINE SDKにも依存しません。

LINEのreply・pushリクエストに含められるメッセージオブジェクトは最大5件です。このライブラリは5件を超えても生成結果をすべて返すため、呼び出し側で配送方法を決めてください。`messages[:5]` のように残りを黙って捨てる使い方は避けてください。また、reply tokenで何度も分割送信できるわけではありません。詳細は公式の[reply API](https://developers.line.biz/ja/reference/messaging-api/#send-reply-message)と[push API](https://developers.line.biz/ja/reference/messaging-api/#send-push-message)を参照してください。

## 公開API

以下の関数は、すべて `line_markdown_parser` からimportできます。

| 関数 | 戻り値・用途 |
| --- | --- |
| `convert_markdown_to_line_messages(text, *, alt_text=None, max_length=1600, max_payload_bytes=28000)` | 設定した上限に合わせて分割したFlex Messageの `list[dict]`。 |
| `build_flex_message(text, *, alt_text=None)` | 分割しない単一のFlex Message。上限を超える場合は `ValueError`。 |
| `build_flex_contents(text)` | 独自bubbleの本文に使うコンポーネントの `list[dict]`。分割とbubbleのサイズ検査は行わない。 |
| `split_long_text(text, max_length=1600, max_payload_bytes=28000)` | 描画用に分割したMarkdownの `list[str]`。 |
| `estimate_flex_payload_size(text)` | 生成したbubbleをコンパクトなJSONにした場合のUTF-8バイト数。 |

主変換関数、`split_long_text`、`build_flex_contents` は、空入力や空白だけの入力に対して `[]` を返します。`build_flex_message` には空でない本文が必要です。`alt_text` は通知やトークリストに表示する代替テキストです。Unicode文字の途中を切らず、最大1,500 UTF-16コード単位に収まるように切り詰めます。省略すると各メッセージの元のチャンクを使用します。明示する場合は空でない文字列を指定し、同じ内容がすべての生成メッセージに使われます。

`max_length` はPythonの文字数に基づく各チャンクの長さの上限であり、LINE APIの文字数制限そのものではありません。`max_payload_bytes` はbubble単体のコンパクトなJSONの大きさを表し、HTTPリクエスト全体の大きさではありません。既定の28,000バイトは、LINE公式のbubble上限30 KBに余裕を持たせた設定です。単一メッセージ生成関数は30,000バイトを上限として検査します。不正な上限値や、分割しても収まらない上限値には `ValueError` が発生します。[Flex Messageの公式仕様](https://developers.line.biz/ja/reference/messaging-api/#flex-message)も参照してください。

すべての公開関数は、UTF-8で200,000バイトを超えるテキスト入力に対して `ValueError` を発生させます。コードフェンスの外では、認識したURLやMarkdownリンクを途中で分割しません。リンク1つが指定した文字数または描画後バイト数の上限に収まらない場合も、途中までのリンクを生成せず `ValueError` を発生させます。許容範囲内で上限を増やすか、アプリケーション側でリンクを短くしてください。

## 描画と対応範囲

- 見出し、リスト、強調、引用、区切り線、コードフェンスなど、よく使うMarkdownをFlexのレイアウトに変換します。
- Markdownの表はコード風のテキスト枠に表示します。ネイティブの対話型テーブルではなく、列の揃い方は端末のフォントに影響されます。
- Markdownの画像はラベルとリンクとして表示します。外部画像の取得や埋め込みは行いません。
- URIアクションは `http` と `https` に対応します。それ以外のスキームを使うMarkdownリンクはラベルを残し、URIアクションを付けません。リンク先の内容や安全性を確認する機能はありません。
- 分割時は読みやすい区切りを優先します。完全なCommonMark互換、任意のネスト、すべてのコードフェンス形式は初版の保証範囲外です。
- 送信、認証情報、SDKオブジェクト、会話状態、デプロイ設定、LLM API呼び出しは含みません。

詳しい契約と制約は[仕様書](docs/spec.md)を参照してください。

## 検証状況

初版では、変換処理とサイズ制御を自動テストで検証しています。実LINE APIへの配送とLINEクライアントでの表示確認は、このリリースでは未実施です。Flex Messageの見え方は端末により異なるため、導入時に[Flex Message Simulator](https://developers.line.biz/flex-simulator/)と対象クライアントで確認してください。クライアントによる違いは公式の[Flex Messageガイド](https://developers.line.biz/ja/docs/messaging-api/using-flex-messages/)にも記載されています。

## 開発

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python scripts/check_public_artifacts.py
python -m build
python -m twine check dist/*
python scripts/check_public_artifacts.py --dist dist
```

貢献方法、公開前の確認、リリース方針は [CONTRIBUTING.md](CONTRIBUTING.md)、変更履歴は [CHANGELOG.md](CHANGELOG.md) を参照してください。

## ライセンス

[MIT](LICENSE)。本プロジェクトは独立したOSSであり、LINEの公式製品ではありません。
