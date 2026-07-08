import { useQuasar } from "quasar";

export function useListDelete(refresh: () => Promise<void> | void) {
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
        const resp = await fetch(`/api/station-lists/${encodeURIComponent(name)}`, {
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

  return { confirmDeleteList };
}
