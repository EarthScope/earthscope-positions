import { useQuasar } from "quasar";

/**
 * Stream/station-list actions (delete + rename) with confirm/prompt dialogs.
 *
 * @param refresh    called after a successful delete/rename to reload the list options
 * @param onRenamed  optional: (oldName, newName) so callers can update any
 *                   currently-selected list references
 */
export function useListDelete(
  refresh: () => Promise<void> | void,
  onRenamed?: (oldName: string, newName: string) => void,
  basePath: string = "/api/stream-lists",
) {
  const $q = useQuasar();

  function confirmDeleteList(name: string) {
    if (!name || name === "all") return;
    $q.dialog({
      title: "Delete list",
      message: `Delete "${name}"? This cannot be undone.`,
      cancel: { flat: true, label: "Cancel" },
      ok: { flat: true, label: "Delete", color: "negative" },
      persistent: true,
    }).onOk(async () => {
      try {
        const resp = await fetch(`${basePath}/${encodeURIComponent(name)}`, {
          method: "DELETE",
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          $q.notify({ type: "negative", message: data.error ?? "Delete failed" });
        } else {
          $q.notify({ type: "positive", message: `Deleted "${name}"` });
          await refresh();
        }
      } catch {
        $q.notify({ type: "negative", message: "Delete failed" });
      }
    });
  }

  function promptRenameList(name: string) {
    if (!name || name === "all") return;
    $q.dialog({
      title: "Rename list",
      message: `New name for "${name}":`,
      prompt: { model: name, type: "text", isValid: (v: string) => !!v.trim() },
      cancel: { flat: true, label: "Cancel" },
      ok: { flat: true, label: "Rename", color: "primary" },
      persistent: true,
    }).onOk(async (raw: string) => {
      const newName = String(raw).trim();
      if (!newName || newName === name) return;
      try {
        const resp = await fetch(
          `${basePath}/${encodeURIComponent(name)}/rename`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ new_name: newName }),
          },
        );
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          $q.notify({ type: "negative", message: data.error ?? "Rename failed" });
          return;
        }
        $q.notify({ type: "positive", message: `Renamed to "${data.name ?? newName}"` });
        await refresh();
        onRenamed?.(name, data.name ?? newName);
      } catch {
        $q.notify({ type: "negative", message: "Rename failed" });
      }
    });
  }

  return { confirmDeleteList, promptRenameList };
}
