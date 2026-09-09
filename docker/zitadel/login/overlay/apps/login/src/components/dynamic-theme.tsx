"use client";

import { EosBrand } from "@/components/eos-brand";
import { BrandingSettings } from "@zitadel/proto/zitadel/settings/v2/branding_settings_pb";
import React, { Children, ReactNode } from "react";
import { ThemeWrapper } from "./theme-wrapper";

/**
 * DynamicTheme renders the EOS login card: a single centered card that matches
 * the EOS web UI (white / slate-900 card on a gray-50 / slate-950 page).
 *
 * Children contract (unchanged from upstream):
 * - First child: title + description block (centered).
 * - Second child: the form (left-aligned).
 * - Single child: rendered as-is.
 */
export function DynamicTheme({
  branding,
  children,
}: {
  children: ReactNode | ((isSideBySide: boolean) => ReactNode);
  branding?: BrandingSettings;
}) {
  // Resolve render-prop children. EOS always uses the single-column layout.
  const actualChildren: ReactNode = React.useMemo(() => {
    if (typeof children === "function") {
      return (children as (isSideBySide: boolean) => ReactNode)(false);
    }
    return children;
  }, [children]);

  const childArray = Children.toArray(actualChildren);
  const titleContent = childArray[0] || null;
  const formContent = childArray[1] || null;
  const hasMultipleChildren = childArray.length > 1;

  return (
    <ThemeWrapper branding={branding}>
      <div className="relative mx-auto w-full max-w-[480px] px-4 py-4">
        <div className="rounded-xl border border-gray-200 bg-white p-10 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <div className="flex flex-col space-y-8">
            <EosBrand />

            {hasMultipleChildren ? (
              <>
                <div className="flex w-full flex-col items-center space-y-1 text-center">{titleContent}</div>
                <div className="w-full">{formContent}</div>
              </>
            ) : (
              <div className="w-full">{actualChildren}</div>
            )}
          </div>
        </div>
      </div>
    </ThemeWrapper>
  );
}
