# line-markdown-parser

LLMが生成したMarkdownを、LINEで読みやすいFlex Messageの辞書に変換するPythonライブラリです。実行時の外部依存はありません。

[English](README.md)

見出し、段落、リスト、引用、コード、リンクをチャットに適したレイアウトに変換し、長文を複数メッセージに分割します。送信処理は利用するアプリケーションで実装します。

## インストール

Python 3.10以上が必要です。GitHubのリリースからインストールできます。PyPIには未公開です。

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
"""

messages = convert_markdown_to_line_messages(markdown)
print(json.dumps(messages, ensure_ascii=False, indent=2))
```

各要素は `type: "flex"`、`altText`、単一の `bubble` を持つ `contents` で構成されます。この辞書をLINE API連携処理に渡してください。ライブラリはネットワーク通信を行わず、LINE SDKにも依存しません。

変換結果は省略せずすべて返します。LINEの[reply](https://developers.line.biz/ja/reference/messaging-api/#send-reply-message)・[push](https://developers.line.biz/ja/reference/messaging-api/#send-push-message)リクエストに含められるメッセージは最大5件のため、呼び出し側で超過時の配送方法とreply tokenの制約に対応してください。

## API

すべての関数は `line_markdown_parser` からimportできます。

| 関数 | 用途 |
| --- | --- |
| `convert_markdown_to_line_messages` | Markdownを分割し、Flex Messageの `list[dict]` を返す。 |
| `build_flex_message` | 分割せず単一メッセージを生成する。サイズ超過はエラー。 |
| `build_flex_contents` | 独自bubble用の本文コンポーネントを生成する。bubbleのサイズ検査は行わない。 |
| `split_long_text` | 分割したMarkdownを `list[str]` で返す。 |
| `estimate_flex_payload_size` | 描画したbubbleのコンパクトなJSONをUTF-8バイト数で測る。 |

変換時の既定値は、チャンクごとに元テキスト1,600文字、描画後28,000バイトです。引数、上限値、代替テキスト、エラー条件は[API仕様書](docs/spec.md)を参照してください。

## 制約

- 表はコード風のテキスト枠で表示します。列の揃い方はクライアントのフォントに依存します。
- 画像はラベルとリンクで表示し、取得や埋め込みは行いません。
- URIアクションは `http` と `https` のみに対応します。リンク先の検証は行いません。
- 完全なCommonMark互換、任意のネスト、すべてのコードフェンス形式には対応していません。
- 自動テストで検証したアルファ版です。実LINEでの配送・表示は未確認のため、導入時に[Flex Message Simulator](https://developers.line.biz/flex-simulator/)と対象のLINEクライアントで確認してください。

## 開発への参加

開発環境と確認コマンドは [CONTRIBUTING.md](CONTRIBUTING.md)、脆弱性報告は [SECURITY.md](SECURITY.md)、変更履歴は [CHANGELOG.md](CHANGELOG.md) を参照してください。

## ライセンス

[MIT](LICENSE)。本プロジェクトは独立したOSSであり、LINEの公式製品ではありません。
