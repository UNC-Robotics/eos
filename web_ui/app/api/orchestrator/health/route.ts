import { NextResponse } from 'next/server';
import { orchestratorGet } from '@/lib/api/orchestrator';

export async function GET() {
  try {
    await orchestratorGet('/health/');
    return NextResponse.json({ connected: true });
  } catch {
    return NextResponse.json({ connected: false });
  }
}
