import type { ContextEventState } from "@/lib/contracts/contextEvents";
import { ContextEventEntry } from "./ContextEventEntry";

interface Props {
  events: ContextEventState[];
}

export function ContextEventLog({ events }: Props) {
  if (events.length === 0) {
    return <p className="text-xs text-gray-400">No events yet.</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      {events.map((event) => (
        <ContextEventEntry key={event.id} event={event} />
      ))}
    </div>
  );
}
