# line-markdown-parser

LLMが生成したMarkdownを、LINEで読みやすいFlex Messageの辞書に変換するPythonライブラリです。実行時の外部依存はありません。

[English](https://github.com/darkgaldoggo/line-markdown-parser/blob/main/README.md)

LINE BOTでの実運用を通じて改善してきた変換処理をもとにしています。

見出し、段落、リスト、引用、コード、リンクをチャットに適したレイアウトに変換し、長文を複数メッセージに分割します。送信処理はアプリケーション側で実装してください。

## インストール

Python 3.10以上が必要です。

```bash
python -m pip install line-markdown-parser
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

各要素は `type: "flex"`、`altText`、1つの `bubble` を含む `contents` で構成されます。この辞書をLINE APIとの連携処理に渡してください。ライブラリはネットワーク通信を行わず、LINE SDKにも依存しません。

変換結果は省略せずすべて返します。LINEの[reply](https://developers.line.biz/ja/reference/messaging-api/#send-reply-message)・[push](https://developers.line.biz/ja/reference/messaging-api/#send-push-message)リクエストで一度に送れるメッセージは最大5件です。これを超える場合の送信方法とリプライトークンの制約には、呼び出し側で対応してください。

## API

すべての関数は `line_markdown_parser` からインポートできます。

| 関数 | 用途 |
| --- | --- |
| `convert_markdown_to_line_messages` | Markdownを分割し、Flex Messageの `list[dict]` を返す。 |
| `build_flex_message` | 分割せずに1件のメッセージを生成する。サイズ超過はエラー。 |
| `build_flex_contents` | 独自のbubble用に本文コンポーネントを生成する。bubbleのサイズ検査は行わない。 |
| `split_long_text` | 分割したMarkdownを `list[str]` で返す。 |
| `estimate_flex_payload_size` | 生成したbubbleをコンパクトなJSONにしたときのUTF-8バイト数を返す。 |

既定では、1チャンクあたり元テキスト1,600文字、bubbleのJSONサイズ28,000バイトを上限に分割します。引数、上限値、代替テキスト、エラー条件は[API仕様書](https://github.com/darkgaldoggo/line-markdown-parser/blob/main/docs/spec.md)を参照してください。

## 制約

- 表はコード風のテキスト枠で表示します。列の揃い方はクライアントのフォントに依存します。
- 画像はラベルとリンクで表示し、取得や埋め込みは行いません。
- URIアクションは `http` と `https` のみに対応します。リンク先の検証は行いません。
- 完全なCommonMark互換と任意のネストには対応していません。コードフェンスもすべての形式に対応しているわけではありません。
- 導入時は、[Flex Message Simulator](https://developers.line.biz/flex-simulator/)と利用するLINEアプリで表示を確認してください。

## 開発への参加

開発環境と確認コマンドは [CONTRIBUTING.md](https://github.com/darkgaldoggo/line-markdown-parser/blob/main/CONTRIBUTING.md)、脆弱性報告は [SECURITY.md](https://github.com/darkgaldoggo/line-markdown-parser/blob/main/SECURITY.md)、変更履歴は [CHANGELOG.md](https://github.com/darkgaldoggo/line-markdown-parser/blob/main/CHANGELOG.md) を参照してください。

## ライセンス

[MIT](https://github.com/darkgaldoggo/line-markdown-parser/blob/main/LICENSE)。本プロジェクトは独立したOSSであり、LINEの公式製品ではありません。
