import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/resources";
import { Modal } from "../components/Modal";
import { QueryBoundary } from "../components/StateViews";
import { useToast } from "../components/Toasts";
import { dateTime } from "../format";

export const UNREAD_KEY = ["notifications", "unread-count"] as const;

export function useUnreadCount() {
  return useQuery({
    queryKey: UNREAD_KEY,
    // The API filters on ?unread=true; page_size=1 because only the count is needed.
    queryFn: async () => (await api.notifications({ unread: true, page_size: 1 })).count,
    refetchInterval: 60_000,
  });
}

export function NotificationsDrawer({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const list = useQuery({ queryKey: ["notifications", "list"], queryFn: () => api.notifications({ page_size: 30 }) });
  const markRead = useMutation({
    mutationFn: (id: string) => api.markRead(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
    onError: (e) => notify(e.message, "error"),
  });

  return (
    <Modal title="Notifications" onClose={onClose} variant="drawer">
      <QueryBoundary query={list} isEmpty={(d) => d.results.length === 0} empty="No notifications yet.">
        {(data) => (
          <ul className="notif-list">
            {data.results.map((n) => (
              <li key={n.id} className={n.is_read ? "notif" : "notif unread"}>
                <p className="notif-msg">{n.message}</p>
                <p className="notif-meta">
                  {n.type.replace(/_/g, " ")} · {dateTime(n.created_at)}
                </p>
                {!n.is_read && (
                  <button type="button" className="btn btn-sm btn-ghost" onClick={() => markRead.mutate(n.id)} disabled={markRead.isPending}>
                    Mark as read
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </QueryBoundary>
    </Modal>
  );
}
