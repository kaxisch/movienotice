const OWNER = "kaxisch";
const REPOSITORY = "movienotice";
const WORKFLOW = "weekly-check.yml";

export default {
  async scheduled(controller, env) {
    if (!env.GITHUB_TOKEN) {
      throw new Error("GITHUB_TOKEN secret is not configured");
    }

    const response = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPOSITORY}/actions/workflows/${WORKFLOW}/dispatches`,
      {
        method: "POST",
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          "User-Agent": "movienotice-weekly-audit-scheduler",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        body: JSON.stringify({ ref: "main" }),
      },
    );

    if (response.status !== 204) {
      const body = await response.text();
      throw new Error(`GitHub workflow dispatch failed (${response.status}): ${body}`);
    }

    console.log(
      JSON.stringify({
        dispatched: WORKFLOW,
        ref: "main",
        scheduledTime: new Date(controller.scheduledTime).toISOString(),
      }),
    );
  },
};
