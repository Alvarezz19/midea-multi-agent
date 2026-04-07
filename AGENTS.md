# AGENTS.md

This file defines repository-specific instructions for Codex.

## Documentation Encoding

- All project documentation is written in Chinese. When reading documentation files, use UTF-8 encoding.

## Context Limits

- If context limitations or conversation compression cause important information to be lost and would likely lead to hallucination, proactively warn the user and ask them to start a new chat/session before proceeding.

## Response Quality

- Do not simply follow the user's proposed line of thinking by default.
- For each question, use your own knowledge and judgment to provide the most appropriate and higher-quality answer when a better approach exists.

## LangGraph Questions

- If a question involves LangGraph, consult the official LangGraph documentation before answering:
- https://docs.langchain.com/oss/python/langgraph
- Base the answer on the relevant official documentation first, then add explanation or recommendations as needed.

## New Technologies And Tools

- If a question involves a new technology, a new tool, or information that may have changed recently, perform a web search before answering.
- Prioritize up-to-date and authoritative sources so the answer is current and accurate.

## Windows Command Line

- The user's computer runs Windows.
- When providing command-line instructions, provide commands that are suitable for Windows.
- In a new terminal session, activate the Conda environment before the first project command:

```powershell
conda activate midea
```

- If multiple commands are needed in a fresh terminal, assume the environment activation step comes first.
