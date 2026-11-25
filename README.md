# LAPIS

Lapis is a local AI assistant that I developed, mostly for my own fun. I was bored, and thought this was an interesting way to spend my time.

Lapis runs on your machine. It connects the model you give it to a set of tools that I have written. And these tools can do a whole lot of things.

All this, bundled into either a CLI interface or an actual UI, however you like it.

## So, what can Lapis do?

Lapis was developed with convenience in mind. I didnt want it to do anything fancy, especially considering I am personally running it on a 4 Billion parameter qwen instruct model. But still, I feel like I pushed the limits of what said model can do. 

- Files - read, write, search, create folders, inspect directory trees, open files in Notepad or VS Code
- Projects - create projects, inspect and modify project files, delete files
- Code - generate and write code using local or cloud-based coding models, run Python files
- Web - search the web, fetch pages, open URLs, and search websites
- Browser - open pages, search the browser, and navigate to specific sites
- YouTube - describe a video or whatever you wanna see /play and Lapis opens it on youtube
- GitHub - open repositories (you have to be very specific though) and user profiles
- LeetCode - open specific problems (just give it the number or the problem name)
- Email - read recent emails, search the inbox, and send/reply to emails
- Reminders - create, list, and cancel reminders
- Todos - add, list, complete, delete, and clear todos
- Spotify - play songs and playlists, queue tracks, pause, and skip
- Excel - read workbooks, create spreadsheets, write cells, and add rows
- Word - create, read, append to, and replace document content
- Desktop - launch applications and trigger Windows notifications
- Research - Not a tool, but a feature. Specify that you wanna research something and Lapis will check out multiple sources, gather a LOT of info, and draft a formatted word file for you to see.

About how Lapis codes: As expected, a 4 bn parameter model is not good at complex coding tasks. I tried 2 workarounds. 
- Delegate coding tasks to a smarted 7bn model
- Or, if you happen to have an OpenRouter API key, delegate it to a OpenRouter model of your choice

Still figuring this part out, so any suggestions are welcome.

Depending on which features you want to use, you may need credentials for:
- Ollama
- OpenRouter
- Spotify
- Gmail
(Discussed as you keep reading)

## Local first

The default setup uses Ollama, so the main conversational model runs locally.

That means you aren't sending every random thing you type to some cloud API just because you wanted your assistant to open a file.

For coding, Lapis can also switch between a local coder and a cloud coder:

`use api key`

and

`use local`

Because sometimes your laptop simply decides that 7B parameters is a personal attack.

## Tool system

Tools are kept separate from the agent itself.
That means adding something new doesn't require rebuilding the entire agent loop.

A tool generally looks like:

user request
     ->
model decides a tool is needed
     ->
tool call
     ->
Lapis executes it
     ->
result goes back to the model
     ->
model continues

This lets Lapis chain multiple tool calls together instead of just one isolated tool call per request.

## Requirements
- Python 3.10+
- Ollama
- a model supported by your machine
- Windows, currently
- optional API keys for cloud features
- optional Spotify credentials for Spotify control
- Whatever is in pyproject.toml

## Installation

Clone the repository:

```
git clone https://github.com/Aravind-808/lapis
cd lapis
pip install -e .
```
Make sure Ollama is installed and pull the model you want to use.

For the current default setup:

`ollama pull qwen3:4b-instruct`
`ollama pull qwen2.5-coder:7b`

Will cost you around 6GB

Then configure your environment variables as needed.

Start Lapis with:

`lapis convo` or `lapis "do x"` in your CLI

or:
`python main.py ui` in the project root to use Lapis with UI

## Some Cool Examples

```
you: play the video where 3blue1brown explains neural nets

lapis:
  - finds the exact video
  - plays it in your browser
```

```
you: make me a python script that downloads youtube videos

lapis:
  - generates the script
  - writes it to a file
```

```
you: check if i got any emails from github

lapis:
  - searches your inbox
  - shows the matching emails
```

```
you: play some kanye on spotify

lapis:
  - searches spotify
  - starts playing

(Note that due to limitations, you must have spotify web already open)
```

## Why

I just wanted to see how far I could push a 4bn parameter model into doing things until it gave up. Some parts are surprisingly good, some parts held together by questionable decisions and optimism. But this is very fun. Thats the whole point.

## Afterword
Things are still being revamped/redesigned. New tools are being added, optimizations in progress. Feel free to clone the repo and go wild! Maybe your system can afford a better LLM than mine.

Bye!