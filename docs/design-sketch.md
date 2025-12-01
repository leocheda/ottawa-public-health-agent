# Weekly Health Briefing - design sketch

- items
  - Collects real-time outbreak data from Ottawa Public Health
  - Analyzes active and recently started outbreaks.
  - Identifies weekly trends.
  - Generates a human-friendly weekly health briefing.
  - Automatically publishes the briefing to social media (Twitter/X, Reddit, Substack, etc.).

### Analyzes active and recently started outbreaks

Because this is analysis of numerical data, an AI agent will perform best if it has access to a code interpreter or Python environment to run analysis scripts.

Best practice for granting such access is to sandbox it to prevent granting unnecessary access to the host system.

One well-supported option for sandboxed LLM code execution is E2B. E2B ships as a Python SDK and as an MCP server. In this case for simplicity I would recommend using the Python SDK and LLM tool calling.

E2B supports selection of a container base image and easy setup of Python packages prior to code execution, so packages like numpy, pandas etc can be installed without providing network access to the LLM from the code environment.

It may also make sense to give the LLM access to run shell commands in the container as in [E2B: Run Bash Code](https://e2b.dev/docs/code-interpreting/supported-languages/bash#run-bash-code). This could be helpful because you could copy the outbreak data CSV into the container filesystem and have the LLM run shell commands to inspect it (e.g. `head`, `wc -l`, `sed`, `awk`, etc) prior to writing analysis code.

An example of using E2B in a tool calling context is available at:

- https://github.com/e2b-dev/e2b-cookbook/blob/main/examples/gpt-4o-python/gpt_4o.ipynb

This can be adapted for use with the Google ADK as in the [Google ADK tool calling examples](https://google.github.io/adk-docs/tools-custom/#example).

### `Identifies weekly trends` and `Generates a human-friendly weekly health briefing`

These tasks (and the previous one) are great candidates for completion via LLM prompting with context, with the code interpreter environment available for any data analysis that is needed.

### Automatically publishes the briefing to social media (Twitter/X, Reddit, Substack, etc.)

The biggest lift for this functionality will be setting up API access to one or more social media platforms. Some of these platforms require setting up an OAuth2 flow to get access tokens for posting, which requires deploying a web service with a stable domain name to handle the OAuth2 redirect. I've previously deployed such a system using Postiz but its a bit painful to set up. If you do this part, I'd recommend focusing on one platform first.

Based on my experience:

- X, LinkedIn, and Reddit defintely require an Oauth setup. Substack doesn't have a developer API.
- Telegram is the easiest to set up because it only requires a bot token.

You could still deploy a server at a stable domain to handle OAuth2 and use that for X and Reddit. Recommend leaving this as the last step after the briefing generation is working.

### References

- [Google ADK](https://github.com/google/adk-python)
- [Google ADK tool calling examples](https://google.github.io/adk-docs/tools-custom/#example)
- [E2B: Run Bash Code](https://e2b.dev/docs/code-interpreting/supported-languages/bash#run-bash-code)
- [Manage Posts: Introduction](https://docs.x.com/x-api/posts/manage-tweets/introduction)
  > Since you are making requests on behalf of a user with the manage Posts endpoints, you must authenticate with either OAuth 1.0a User Context or OAuth 2.0 Authorization Code with PKCE, and use user Access Tokens associated with a user that has authorized your App. To generate this user Access Token with OAuth 1.0a, you can use the 3-legged OAuth flow. To generate a user Access Token with OAuth 2.0, you can use the Authorization Code with PKCE grant flow.
  - [X: Create or Edit Post](https://docs.x.com/x-api/posts/create-post)
- [Reddit API: Resources](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki)
  > Reddit requires OAuth for authentication
- [Reddit API: Submit](https://www.reddit.com/dev/api/#POST_api_submit)
