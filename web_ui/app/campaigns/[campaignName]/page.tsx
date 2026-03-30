import { notFound } from 'next/navigation';
import { getCampaignWithDetails } from '@/features/campaigns/api/campaignDetails';
import { CampaignExecutionView } from '@/features/campaigns/components/CampaignExecutionView';

export const dynamic = 'force-dynamic';

interface CampaignDetailPageProps {
  params: Promise<{
    campaignName: string;
  }>;
}

export default async function CampaignDetailPage({ params }: CampaignDetailPageProps) {
  const { campaignName } = await params;
  const decodedName = decodeURIComponent(campaignName);

  const { campaign, samples, protocolRuns } = await getCampaignWithDetails(decodedName);

  if (!campaign) {
    notFound();
  }

  return <CampaignExecutionView campaign={campaign} initialSamples={samples} initialProtocolRuns={protocolRuns} />;
}
