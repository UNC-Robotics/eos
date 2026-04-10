import { SimulatorClient } from '@/features/simulator/components/SimulatorClient';

export default function SimulatorPage() {
  return (
    <div className="container mx-auto px-6 py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Simulator</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-1">
          Run scheduling simulations and visualize execution timelines
        </p>
      </div>
      <SimulatorClient />
    </div>
  );
}
