import { useHomeConfig } from '../../hooks/useHomeConfig';
import { OverviewPage } from '../../pages/OverviewPage';
import { HomeSetupPage } from '../../pages/HomeSetupPage';

/** Home route: dashboard once the home is set up, otherwise first-time setup. (DataGate ensures data is loaded.) */
export function HomeGate() {
  const { config } = useHomeConfig();
  return config.isConfigured ? <OverviewPage /> : <HomeSetupPage isEditMode={false} />;
}
