import { AssistantStatus } from "../screens/App";

type Props = {
  status: AssistantStatus;
};

export function Orb({ status }: Props) {
  return (
    <div className={`orb orb-${status}`} aria-label="Статус ассистента">
      <div className="orb-ring orb-ring-outer" />
      <div className="orb-ring orb-ring-middle" />
      <div className="orb-core" />
    </div>
  );
}

