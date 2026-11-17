import { useCallback, useEffect, useState } from 'react';
import { listJobs } from './api.js';

// Zentraler Job-Hook: hält die Jobliste aktuell und pollt nur, solange
// mindestens ein Job queued/running ist (1200 ms). Danach keine Endlos-Polls.
export default function useJobs(limit = 50, intervalMs = 1200) {
  const [jobs, setJobs] = useState([]);

  const active = jobs.some(
    (job) => job.status === 'queued' || job.status === 'running',
  );

  const refreshJobs = useCallback(async () => {
    try {
      const list = await listJobs(limit);
      setJobs(list);
      return list;
    } catch {
      return null;
    }
  }, [limit]);

  useEffect(() => {
    if (!active) return undefined;
    let stopped = false;

    const tick = async () => {
      try {
        const list = await listJobs(limit);
        if (!stopped) setJobs(list);
      } catch {
        /* Der nächste Tick versucht es erneut. */
      }
    };

    tick();
    const timer = setInterval(tick, intervalMs);

    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [active, limit, intervalMs]);

  return { jobs, setJobs, refreshJobs };
}