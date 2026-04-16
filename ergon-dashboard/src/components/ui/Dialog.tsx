"use client";

/**
 * Minimal modal dialog built on the native <dialog> element.
 *
 * - Backdrop click closes the dialog (native ::backdrop).
 * - Escape closes for free (native behaviour).
 * - `open` drives `showModal()` / `close()`.
 * - Styled entirely via Tailwind; no Radix / shadcn.
 */

import { useEffect, useRef } from "react";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  /**
   * Optional extra classes appended to the dialog content box. Default sizing
   * covers most viewers; viewers that need full height can widen here.
   */
  className?: string;
}

export function Dialog({ open, onClose, title, children, className = "" }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog === null) return;
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  // Close when the native dialog fires cancel (Escape) or close events.
  useEffect(() => {
    const dialog = ref.current;
    if (dialog === null) return;
    const handleCancel = (e: Event) => {
      e.preventDefault();
      onClose();
    };
    const handleClose = () => {
      onClose();
    };
    dialog.addEventListener("cancel", handleCancel);
    dialog.addEventListener("close", handleClose);
    return () => {
      dialog.removeEventListener("cancel", handleCancel);
      dialog.removeEventListener("close", handleClose);
    };
  }, [onClose]);

  // Backdrop click: native <dialog> receives the click target = dialog itself.
  const handleDialogClick = (event: React.MouseEvent<HTMLDialogElement>) => {
    if (event.target === ref.current) {
      onClose();
    }
  };

  return (
    <dialog
      ref={ref}
      onClick={handleDialogClick}
      className={
        "backdrop:bg-black/50 backdrop:backdrop-blur-sm " +
        "rounded-2xl bg-white p-0 shadow-2xl dark:bg-gray-900 " +
        "w-[90vw] max-w-5xl max-h-[90vh] " +
        "text-gray-900 dark:text-white"
      }
    >
      <div
        className={`flex h-full max-h-[90vh] flex-col ${className}`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between gap-4 border-b border-gray-200 px-5 py-3 dark:border-gray-800">
          <h2 className="truncate text-sm font-semibold text-gray-900 dark:text-white">
            {title ?? ""}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-white"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-auto">{children}</div>
      </div>
    </dialog>
  );
}
