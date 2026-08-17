import { useEffect, useState } from "react";

/**
 * Returns `value`, but delayed until it has stopped changing for `delayMs`.
 *
 * Used on admin search boxes that trigger a full API request per change -
 * without this, each keystroke fired its own fetch, and a fast typist could
 * have several in flight racing each other.
 */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);

  return debounced;
}
