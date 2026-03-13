import React from "react";

/**
 * Purpose: Describe what `Footer` does within the frontend flow.
 * Args/Params:
 * - None.
 * Returns:
 * - Varies by usage (UI element, transformed payload, or helper value).
 * Raises/Exceptions:
 * - Propagates runtime errors when invalid input/state is provided.
 * Examples:
 * - `Footer()`
 */
export default function Footer() {
  return (
    <footer className="px-6 py-12 text-center text-sm text-gray-600 dark:text-gray-400 mt-24 bg-gray-50 dark:bg-gray-900/40 border-t border-gray-100 dark:border-gray-800">
      <p>
        Copyright © AGENTS.md a Series of LF Projects, LLC
        <br />
        For web site terms of use, trademark policy and other project policies please see{" "}
        <a href="https://lfprojects.org" target="_blank" className="underline hover:no-underline">
          https://lfprojects.org
        </a>
        .
      </p>
    </footer>
  );
}
