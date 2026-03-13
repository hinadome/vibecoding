import React from "react";
import Section from "@/components/Section";
import CodeExample from "@/components/CodeExample";
import ExampleListSection from "@/components/ExampleListSection";

interface ExamplesSectionProps {
  contributorsByRepo: Record<string, { avatars: string[]; total: number }>;
}

/**
 * Purpose: Describe what `ExamplesSection` does within the frontend flow.
 * Args/Params:
 * - destructured_param: Value consumed by `ExamplesSection`.
 * Returns:
 * - Varies by usage (UI element, transformed payload, or helper value).
 * Raises/Exceptions:
 * - Propagates runtime errors when invalid input/state is provided.
 * Examples:
 * - `ExamplesSection(value)`
 */
export default function ExamplesSection({ contributorsByRepo }: ExamplesSectionProps) {
  return (
    <Section id="examples" title="Examples" className="py-12" center>
      {/* Wide code example */}
      <div className="mb-4">
        <CodeExample compact />
      </div>

      {/* Repo cards */}
      <ExampleListSection contributorsByRepo={contributorsByRepo} standalone />
    </Section>
  );
}
