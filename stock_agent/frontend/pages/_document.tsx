import { Html, Head, Main, NextScript } from "next/document";

/**
 * Purpose: Describe what `Document` does within the frontend flow.
 * Args/Params:
 * - None.
 * Returns:
 * - Varies by usage (UI element, transformed payload, or helper value).
 * Raises/Exceptions:
 * - Propagates runtime errors when invalid input/state is provided.
 * Examples:
 * - `Document()`
 */
export default function Document() {
  return (
    <Html lang="en">
      <Head>
        <link
          rel="icon"
          href="/favicon-light.png"
          media="(prefers-color-scheme: light)"
        />
        <link
          rel="icon"
          href="/favicon-dark.png"
          media="(prefers-color-scheme: dark)"
        />
      </Head>
      <body className="antialiased">
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
