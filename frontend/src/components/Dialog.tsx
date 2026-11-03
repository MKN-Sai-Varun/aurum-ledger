import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

interface DialogProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export default function Dialog({ title, onClose, children }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (node && !node.open) node.showModal();
    return () => {
      if (node && node.open) node.close();
    };
  }, []);

  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby="dialog-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="dialog-body">
        <header className="dialog-head">
          <h2 id="dialog-title" className="card-title">
            {title}
          </h2>
          <button className="btn btn-quiet" type="button" onClick={onClose}>
            Close
          </button>
        </header>
        {children}
      </div>
    </dialog>
  );
}