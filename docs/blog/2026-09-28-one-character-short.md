# One character short

An agent was asked to send a question in a Feishu chat. It clicked the empty
message box and ran `co browser keyboard_type` with a line of Chinese. The box
then read "数据管线测试岗评分最高的数据管线测试岗评分最高的3个人是谁？", with the
first words written twice, under a real person's name. It happened three times
in a row, each time after the box had been cleared. When the same line followed
an ASCII prefix like "Q: ", or came after a mention, it came out right.

The duplicated part was not random. It was exactly the first run of Chinese
characters, up to the "3". `keyboard_type` types Latin letters one key at a
time, but it pastes Chinese, because that is how people usually enter it. If a
field refuses the paste, the text is composed through the IME instead. To tell
whether the paste worked, it checked that the field had grown by the full
length of the text. That check is what went wrong.

An empty rich-text editor, like Feishu's or anything built on Slate, is not
really empty. The empty line holds a zero-width character so the cursor has
somewhere to sit, and the first insert replaces it. So the paste landed and
twelve characters appeared, but one invisible character went away, and the
field had grown by eleven. The check decided the paste had been refused and
typed the same twelve characters again through the IME. After a prefix, the
placeholder was already gone and the numbers added up, which is why only the
empty box ever showed the problem.

We reproduced it in a real Chrome with a twenty-line editor that behaves the
same way, and got the doubled text on the first try. The fix changes the
question the check asks. It no longer asks whether the field grew by the full
length; it asks whether the field's text changed at all. It waits a moment
for editors that insert on a later frame, and only an untouched field counts
as a refusal. A paste that lands only partly is left alone. A short message is
something the screenshot catches, but a doubled one gets sent under someone's
name.

The lesson is about checks that count. "Did it grow by N" builds in the
assumption that nothing else in the field moves, and editors move things all
the time. When a check exists to decide whether to do something again, it
should ask the question whose wrong answer does the least harm.
