type Tone = "good" | "warn" | "bad" | "idle";

type Props = {
  label: string;
  value: string;
  tone?: Tone;
};

export function StatusPill({ label, value, tone = "idle" }: Props) {
  return (
    <div className={`status-pill status-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

