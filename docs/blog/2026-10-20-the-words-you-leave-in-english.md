# The words you leave in English

People who work in Chinese and English do not translate everything. A
review is still a "review" and a pull request is a "PR". In the cached Chinese
pages, the model translated those words anyway. One capstone project became
"顶点项目", which no one in that program says.

We did not want a glossary someone has to maintain, so the reader takes one
from the owner's own writing. REM already reads the mail the owner sent and
the turns they typed to detect their languages. It now also checks which words
from a fixed technical vocabulary (PR, agent, demo, review, release, workflow
and about forty others) appear in Latin letters inside the owner's own Chinese
messages. A word that does so in at least two separate messages goes into the
translation prompt as "keep these terms in English". The vocabulary is fixed
so that only those words can reach a prompt. Names and private words from the
mail cannot. On a real notebook the owner's list came out as 28 terms, including agent, PR,
review, workflow and demo. A new list applies to new translations only. Pages
already cached are not translated again just because the glossary changed.

Two display fixes came with it. The home page cards split a thread at its
first semicolon into a headline and a detail line. Chinese translations use
"；", so the detail line began with a stray semicolon. And the roles and companies
under a person's name came from the English Facts lines. They now come
from the translated Facts, whose labels stay in English so the parser still
reads them.
