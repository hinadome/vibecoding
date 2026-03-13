import type { NextApiRequest, NextApiResponse } from "next";

type Data =
  | {
      outputText: string;
    }
  | {
      error: string;
    };

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse<Data>
) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ error: "Method not allowed" });
  }

  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return res.status(500).json({
      error: "OPENAI_API_KEY is missing on the server.",
    });
  }

  const prompt = typeof req.body?.prompt === "string" ? req.body.prompt.trim() : "";
  if (!prompt) {
    return res.status(400).json({ error: "Prompt is required." });
  }

  try {
    const response = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: "gpt-4.1-mini",
        input: prompt,
      }),
    });

    if (!response.ok) {
      const details = await response.text();
      return res.status(response.status).json({
        error: `OpenAI request failed: ${details.slice(0, 500)}`,
      });
    }

    const data = (await response.json()) as { output_text?: string };
    return res.status(200).json({ outputText: data.output_text ?? "" });
  } catch {
    return res.status(500).json({ error: "Unexpected server error." });
  }
}
