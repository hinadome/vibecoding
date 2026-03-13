import { FormEvent, useState } from "react";

/**
 * Purpose: Describe what `HackathonDemoPage` does within the frontend flow.
 * Args/Params:
 * - None.
 * Returns:
 * - Varies by usage (UI element, transformed payload, or helper value).
 * Raises/Exceptions:
 * - Propagates runtime errors when invalid input/state is provided.
 * Examples:
 * - `HackathonDemoPage()`
 */
export default function HackathonDemoPage() {
  const [prompt, setPrompt] = useState("Write a 3-line product pitch for a hackathon project called Nevermind.");
  const [output, setOutput] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setOutput("");

    try {
      const response = await fetch("/api/hackathon-demo", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ prompt }),
      });

      const data = (await response.json()) as { outputText?: string; error?: string };

      if (!response.ok) {
        throw new Error(data.error || "Request failed.");
      }

      setOutput(data.outputText || "(No output)");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12 font-sans">
      <h1 className="text-3xl font-bold">Nevermind Hackathon Demo</h1>
      <p className="mt-3 text-sm text-gray-700">
        This sample sends your prompt to a server-side Next.js API route, which calls OpenAI with
        `OPENAI_API_KEY` from environment variables.
      </p>

      <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4">
        <label htmlFor="prompt" className="text-sm font-semibold">
          Prompt
        </label>
        <textarea
          id="prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          className="min-h-36 rounded border border-gray-300 p-3"
          placeholder="Describe what you want the model to do"
        />

        <button
          type="submit"
          className="w-fit rounded bg-black px-4 py-2 text-white disabled:opacity-50"
          disabled={loading}
        >
          {loading ? "Generating..." : "Run Demo"}
        </button>
      </form>

      {error ? (
        <div className="mt-6 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">{error}</div>
      ) : null}

      {output ? (
        <section className="mt-6">
          <h2 className="text-lg font-semibold">Output</h2>
          <pre className="mt-2 whitespace-pre-wrap rounded border border-gray-200 bg-gray-50 p-4 text-sm">
            {output}
          </pre>
        </section>
      ) : null}
    </main>
  );
}
