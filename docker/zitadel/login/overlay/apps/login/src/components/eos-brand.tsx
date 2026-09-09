import Image from "next/image";
import eosLogo from "./eos-logo.png";

// EOS brand header shown on every login step. The logo already contains the
// "EOS" wordmark, so we pair it only with the system subtitle.
export function EosBrand() {
  return (
    <div className="flex flex-col items-center text-center">
      <Image
        src={eosLogo}
        alt="EOS"
        priority
        unoptimized
        className="h-24 w-auto rounded-xl shadow-sm ring-1 ring-black/5 dark:ring-white/10"
      />
      <p className="mt-4 text-lg font-medium text-gray-900 dark:text-white">Experiment Orchestration System</p>
    </div>
  );
}
