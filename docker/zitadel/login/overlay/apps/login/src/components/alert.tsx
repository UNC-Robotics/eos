import { ExclamationTriangleIcon, InformationCircleIcon } from "@heroicons/react/24/outline";
import { clsx } from "clsx";
import { ReactNode } from "react";

type Props = {
  children: ReactNode;
  type?: AlertType;
};

export enum AlertType {
  ALERT,
  INFO,
}

// Errors use EOS red; yellow would clash with the dark-mode primary color.
const red =
  "border-red-600/40 dark:border-red-500/30 bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300";
const neutral = "border-divider-light dark:border-divider-dark bg-black/5 text-gray-600 dark:bg-white/10 dark:text-gray-200";

export function Alert({ children, type = AlertType.ALERT }: Props) {
  return (
    <div
      className={clsx("flex scroll-px-40 flex-row items-center justify-center rounded-md border py-2 pr-2", {
        [red]: type === AlertType.ALERT,
        [neutral]: type === AlertType.INFO,
      })}
    >
      {type === AlertType.ALERT && <ExclamationTriangleIcon className="mr-2 ml-2 h-5 w-5 flex-shrink-0" />}
      {type === AlertType.INFO && <InformationCircleIcon className="mr-2 ml-2 h-5 w-5 flex-shrink-0" />}
      <span className="w-full text-sm">{children}</span>
    </div>
  );
}
