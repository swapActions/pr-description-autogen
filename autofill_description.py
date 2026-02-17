#!/usr/bin/env python3
import argparse
import os
import sys

import requests
from openai import OpenAI

SAMPLE_PROMPT = """
Write a pull request description focusing on the motivation behind the change and why it improves the project.
Go straight to the point.

The title of the pull request is "Fix sorting on "Principal Investigator" and "PI Email" for proposal table" and the following changes took place:

Changes in file diff --git a/apps/backend/src/datasources/postgres/ProposalDataSource.ts b/apps/backend/src/datasources/postgres/ProposalDataSource.ts
index 425b38954..4014fafd6 100644
--- a/apps/backend/src/datasources/postgres/ProposalDataSource.ts
+++ b/apps/backend/src/datasources/postgres/ProposalDataSource.ts
@@ -52,8 +52,6 @@ const fieldMap: { [key: string]: string } = {
   statusName: 'proposal_table_view.proposal_status_id',
   proposalId: 'proposal_table_view.proposal_id',
   title: 'title',
-  submitted: 'proposal_table_view.submitted',
-  notified: 'proposal_table_view.notified',
 };

 export async function calculateReferenceNumber(
diff --git a/apps/frontend/src/components/proposal/ProposalTableOfficer.tsx b/apps/frontend/src/components/proposal/ProposalTableOfficer.tsx
index d495d9fed..00dff28a2 100644
--- a/apps/frontend/src/components/proposal/ProposalTableOfficer.tsx
+++ b/apps/frontend/src/components/proposal/ProposalTableOfficer.tsx
@@ -118,7 +118,6 @@ let columns: Column<ProposalViewData>[] = [
   {
     title: 'Principal Investigator',
     field: 'principalInvestigator',
-    sorting: false,
     emptyValue: '-',
     render: (proposalView) => {
       if (
@@ -134,7 +133,6 @@ let columns: Column<ProposalViewData>[] = [
   {
     title: 'PI Email',
     field: 'principalInvestigator.email',
-    sorting: false,
     emptyValue: '-',
   },
   {
"""

GOOD_SAMPLE_RESPONSE = """
## Description
This PR addresses malfunctioning sorting functionality on "Principal Investigator" and "PI Email" columns by disabling sorting on them.

## Motivation and Context
The sorting functionality on "Principal Investigator" and "PI Email" columns was malfunctioning, causing unexpected results and confusion for users.

## Changes
- Disables sorting on "Principal Investigator" and "PI Email" columns.
"""


def _extract_jira_description(issue_data):
    description = ""
    fields = issue_data.get("fields", {})
    raw_description = fields.get("description")

    if isinstance(raw_description, str):
        return raw_description.strip()

    if isinstance(raw_description, dict):
        for block in raw_description.get("content", []):
            if block.get("type") != "paragraph":
                continue
            for part in block.get("content", []):
                if part.get("type") == "text":
                    description += part.get("text", "") + " "

    return description.strip()


def _fetch_jira_task_description(jira_base_url, jira_issue_key, jira_api_token):
    if not jira_base_url or not jira_issue_key or not jira_api_token:
        return ""

    url = f"{jira_base_url}/rest/api/2/issue/{jira_issue_key}"
    headers = {
        "Authorization": f"Bearer {jira_api_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=20)
    except requests.exceptions.RequestException as error:
        print(f"Failed to fetch Jira issue: {error}")
        return ""

    print(
        f"Jira issue description request status code: {response.status_code}")

    if response.status_code != 200:
        print(
            f"Failed to fetch Jira issue description. Response: {response.text}")
        return ""

    try:
        issue_data = response.json()
    except ValueError:
        print("Failed to parse Jira response as JSON")
        return ""

    return _extract_jira_description(issue_data)


def _build_prompt(pull_request_title, task_description, pull_request_files):
    exclude_filenames = {"package-lock.json"}

    prompt = f"""
Write a concise pull request description focusing on the motivation behind the change so that it is helpful for the reviewer to understand.
Go straight to the point, avoid verbosity.
Pull request description should consist of three sections:
## Description
This is the concise high level description in one short sentence of the PR. (what).

## Motivation and Context
Why is this change required? Explain in one short sentence. What problem does it solve? (why)

## Changes
Go through step by step. What types of changes does your code introduce? Keep it short focusing only on maximum 3 most important changes. (how)

Below is additional context regarding task from the Jira ticket. Use them to write better description and motivation:
{task_description}

The title of the pull request is "{pull_request_title}" and the following changes took place:
"""

    for pull_request_file in pull_request_files:
        if "patch" not in pull_request_file:
            continue

        filename = pull_request_file.get("filename", "")
        if filename in exclude_filenames:
            continue

        patch = pull_request_file["patch"]
        prompt += f"\nChanges in file {filename}: {patch}\n"

    max_allowed_tokens = 2048
    characters_per_token = 4
    max_allowed_characters = max_allowed_tokens * characters_per_token
    if len(prompt) > max_allowed_characters:
        prompt = prompt[:max_allowed_characters]

    return prompt


def _get_sample_prompt_from_env():
    return os.environ.get(
        "INPUT_MODEL_SAMPLE_PROMPT",
        os.environ.get("INPUT_SAMPLE_PROMPT", SAMPLE_PROMPT),
    )


def _get_sample_response_from_env():
    return os.environ.get(
        "INPUT_MODEL_SAMPLE_RESPONSE",
        os.environ.get("INPUT_SAMPLE_RESPONSE", GOOD_SAMPLE_RESPONSE),
    )


def main():
    parser = argparse.ArgumentParser(
        description="Use ChatGPT to generate a description for a pull request."
    )
    parser.add_argument("--github-api-url", type=str,
                        required=True, help="The GitHub API URL")
    parser.add_argument("--github-repository", type=str,
                        required=True, help="The GitHub repository")
    parser.add_argument("--pull-request-id", type=int,
                        required=True, help="The pull request ID")
    parser.add_argument("--github-token", type=str,
                        required=True, help="The GitHub token")
    parser.add_argument("--openai-api-key", type=str,
                        required=True, help="The OpenAI API key")
    parser.add_argument("--jira-api-token", type=str,
                        required=True, help="Jira API token")
    parser.add_argument("--jira-issue-key", type=str,
                        required=True, help="Jira issue key")
    parser.add_argument("--jira-base-url", type=str,
                        required=True, help="Jira base URL")
    parser.add_argument(
        "--allowed-users",
        type=str,
        required=False,
        help="A comma-separated list of GitHub usernames that are allowed to trigger the action, empty or missing means all users are allowed",
    )

    args = parser.parse_args()

    github_api_url = args.github_api_url
    repo = args.github_repository
    github_token = args.github_token
    pull_request_id = args.pull_request_id
    openai_api_key = args.openai_api_key
    jira_api_token = args.jira_api_token
    jira_issue_key = args.jira_issue_key
    jira_base_url = args.jira_base_url

    allowed_users = os.environ.get("INPUT_ALLOWED_USERS", "")
    allowed_users = allowed_users.split(",") if allowed_users else []

    open_ai_model = os.environ.get("INPUT_OPENAI_MODEL", "gpt-4.1-nano")
    max_prompt_tokens = int(os.environ.get("INPUT_MAX_TOKENS", "1000"))
    model_temperature = float(os.environ.get("INPUT_TEMPERATURE", "0.6"))
    model_sample_prompt = _get_sample_prompt_from_env()
    model_sample_response = _get_sample_response_from_env()

    authorization_header = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {github_token}",
    }

    pull_request_url = f"{github_api_url}/repos/{repo}/pulls/{pull_request_id}"
    pull_request_result = requests.get(
        pull_request_url, headers=authorization_header, timeout=20)
    if pull_request_result.status_code != requests.codes.ok:
        print("Request to get pull request data failed: " +
              str(pull_request_result.status_code))
        return 1

    try:
        pull_request_data = pull_request_result.json()
    except ValueError:
        print("Failed to parse pull request response as JSON")
        return 1

    if pull_request_data.get("body"):
        print("Pull request already has a description, skipping")
        return 0

    if allowed_users:
        pr_author = pull_request_data.get("user", {}).get("login", "")
        if pr_author not in allowed_users:
            print(
                f"Pull request author {pr_author} is not allowed to trigger this action")
            return 0

    pull_request_title = pull_request_data.get("title", "")

    pull_request_files = []
    for page_num in range(1, 11):
        pull_files_url = f"{pull_request_url}/files?page={page_num}&per_page=30"
        pull_files_result = requests.get(
            pull_files_url, headers=authorization_header, timeout=20)

        if pull_files_result.status_code != requests.codes.ok:
            print("Request to get list of files failed with error code: " +
                  str(pull_files_result.status_code))
            return 1

        try:
            pull_files_chunk = pull_files_result.json()
        except ValueError:
            print("Failed to parse files response as JSON")
            return 1

        if len(pull_files_chunk) == 0:
            break

        pull_request_files.extend(pull_files_chunk)

    task_description = _fetch_jira_task_description(
        jira_base_url, jira_issue_key, jira_api_token)

    completion_prompt = _build_prompt(
        pull_request_title=pull_request_title,
        task_description=task_description,
        pull_request_files=pull_request_files,
    )

    prompt_text = (
        "You are a world class expert full stack web developer having experience with nodejs, "
        "typescript, express who writes pull request descriptions adding 'description' and "
        "'how has this been tested' sections.\n\n"
        f"User: {model_sample_prompt}\n"
        f"Assistant: {model_sample_response}\n"
        f"User: {completion_prompt}\n"
        "Assistant:"
    )

    print(f"Using model: '{open_ai_model}'")
    client = OpenAI(api_key=openai_api_key)

    request_payload = {
        "model": open_ai_model,
        "input": prompt_text,
        "max_output_tokens": max_prompt_tokens,
    }

    # GPT-5.2-Codex and some GPT-5 configurations do not support temperature.
    # Keep interface compatibility (INPUT_TEMPERATURE) but only send temperature
    # for models/endpoints where it is accepted.
    model_name_lower = open_ai_model.lower()
    should_send_temperature = not (
        "codex" in model_name_lower
        or model_name_lower.startswith("gpt-5")
    )
    if should_send_temperature:
        request_payload["temperature"] = model_temperature
    else:
        print(
            "Skipping temperature parameter for GPT-5/Codex model compatibility."
        )

    try:
        openai_response = client.responses.create(**request_payload)
    except Exception as error:
        error_message = str(error)
        unsupported_temperature = (
            "Unsupported parameter" in error_message
            and "temperature" in error_message
        )

        if unsupported_temperature and "temperature" in request_payload:
            print(
                "Model rejected temperature. Retrying request without temperature."
            )
            del request_payload["temperature"]
            try:
                openai_response = client.responses.create(**request_payload)
            except Exception as retry_error:
                print(
                    f"Responses API failed for model '{open_ai_model}' after retry: {retry_error}"
                )
                return 1
        else:
            print(f"Responses API failed for model '{open_ai_model}': {error}")
            return 1

    generated_pr_description = (openai_response.output_text or "").strip()

    redundant_prefix = "This pull request "
    if generated_pr_description.startswith(redundant_prefix):
        generated_pr_description = generated_pr_description[len(
            redundant_prefix):]
        if generated_pr_description:
            generated_pr_description = generated_pr_description[0].upper(
            ) + generated_pr_description[1:]

    how_has_this_been_tested_section = (
        "## How Has This Been Tested?\n\n"
        "<!--- Please describe in detail how you tested your changes. -->\n"
        "<!--- Include details of your testing environment, and the tests you ran to -->\n"
        "<!--- see how your change affects other areas of the code, etc. -->"
    )
    fixes_jira_issue_section = (
        f"## Fixes Jira Issue\n\n[{jira_base_url}/browse/{jira_issue_key}]"
        f"({jira_base_url}/browse/{jira_issue_key})"
    )
    depends_on_section = "## Depends On\n\n<!--- Does this PR depend on another PR that should be merged first or at the same time -->"
    tests_section = (
        "## Tests included/Docs Updated?\n\n"
        "<!--- Go over all the following points, and put an `x` in all the boxes that apply. -->\n\n"
        "- [ ] I have added tests to cover my changes.\n"
        "- [ ] All relevant doc has been updated"
    )

    generated_pr_description = (
        f"{generated_pr_description}\n\n"
        f"{how_has_this_been_tested_section}\n\n"
        f"{fixes_jira_issue_section}\n\n"
        f"{depends_on_section}\n\n"
        f"{tests_section}"
    )

    print(f"Generated pull request description: '{generated_pr_description}'")

    issues_url = f"{github_api_url}/repos/{repo}/issues/{pull_request_id}"
    update_pr_description_result = requests.patch(
        issues_url,
        headers=authorization_header,
        json={"body": generated_pr_description},
        timeout=20,
    )

    if update_pr_description_result.status_code != requests.codes.ok:
        print(
            "Request to update pull request description failed: "
            + str(update_pr_description_result.status_code)
        )
        print("Response: " + update_pr_description_result.text)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
