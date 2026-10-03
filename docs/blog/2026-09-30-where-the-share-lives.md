# Where the share lives

The owner works with several groups of students. One group builds an Android
app on top of our frontend. Another is interested in how co rem itself
thinks. Every day something changes that one group or the other should know
about, and co rem already files it into the project pages. The question was how
it should reach them.

Our first answer was a system. Each share would get its own configuration page.
Students would be organised into groups, and each group would have a page
saying what it cares about. There would even be a card each notebook sends to
its contacts, so that the other person's notebook could subscribe by itself.
It made a tidy diagram, with four new kinds of thing.

The owner took it apart in two sentences. First: the share belongs on the
page. When the frontend project changes, the owner is looking at the frontend
page. That is where "who should hear about this" belongs, not in a
configuration file somewhere else that has to be kept in step with it. Second:
groups add nothing. A line with five students' addresses already is the group.

So a project page grows one section:

```markdown
## Share
- to: vicky@uni.edu, tom@uni.edu · every: day · about: frontend components and API changes
```

Each night, co rem reads every Share line in the notebook, groups the lines by
address, and checks what changed. A student on two lines gets one email with
two sections. A quiet day sends nothing and costs nothing. Each student gets
their own copy, so addresses stay private, replies stay separate, and "stop"
removes one person, not the class.

Two rules keep it safe. The addresses and the schedule are fixed fields that
code reads, and only the "about" text reaches the model. And the section
belongs to the owner: the nightly upkeep that rewrites pages must leave it
exactly as it was.

The cards and subscriptions did not disappear. They moved to 1.9.1, where
they will add lines to the same Share section rather than live beside it. The
lesson was the one we keep relearning: before adding a place to store a
decision, look at where the person already is when they make it.
