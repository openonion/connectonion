# The page it wrote and threw away

At 05:00 on Monday the Wiki finished investigating one of the owner's
projects. It had gathered the sessions, called the model and written the
page. When it went to save the page, the scheduled overnight update had
started a minute earlier and was holding the notebook. The investigation
printed "Wiki is busy" and exited. The page was never saved, and the model
time spent writing it was lost.

The lock that one writer holds while it changes the notebook never waits.
That was right for the scheduled update, because a tick that finds the
notebook busy tries again five minutes later. An investigation has no next
tick. Now saving a finished page waits for the notebook for up to half an
hour. If it still can't save, the error says where the finished page is
kept.

The same release fixes an older version of the same mistake. `init` used to
write every default into the notebook's settings file, and a saved setting
always wins. So a notebook made on 20 September kept that day's model,
which ChatGPT logins had since stopped accepting, and its overnight update
failed for four nights in a row. A setting equal to a default we have since
replaced is now read as unset, and one the owner chose with `config set` is
still kept.
