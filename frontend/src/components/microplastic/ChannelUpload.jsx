import { ImageUp, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

/**
 * One polarimetric channel input.
 *
 * The three channels are separate inputs on purpose: the model was trained on
 * R/A/P stacks, and a single reflectance image scores at chance. Making the
 * requirement explicit in the UI is more honest than accepting one file and
 * quietly producing a meaningless answer.
 */
export default function ChannelUpload({ channel, description, file, onChange }) {
  const inputRef = useRef(null);
  const [preview, setPreview] = useState(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return undefined;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const accept = (candidate) => {
    if (candidate && candidate.type.startsWith('image/')) onChange(candidate);
  };

  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <label htmlFor={`channel-${channel}`} className="text-xs font-medium text-mist">
          <span className="font-mono text-water">{channel}</span> — {description}
        </label>
        {file && (
          <button
            onClick={() => onChange(null)}
            className="text-[11px] text-mist-faint hover:text-alert-light flex items-center gap-1"
          >
            <X size={11} />
            Clear
          </button>
        )}
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          accept(e.dataTransfer.files?.[0]);
        }}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        role="button"
        tabIndex={0}
        aria-label={`Upload the ${channel} channel image`}
        className={`relative rounded-xl border border-dashed aspect-square flex flex-col
          items-center justify-center gap-2 cursor-pointer transition-colors overflow-hidden
          ${
            dragging
              ? 'border-water bg-water/[0.08]'
              : file
                ? 'border-water/30 bg-ink'
                : 'border-white/15 bg-ink hover:border-water/30'
          }`}
      >
        {preview ? (
          <img
            src={preview}
            alt={`${channel} channel preview`}
            className="absolute inset-0 w-full h-full object-contain p-1.5"
          />
        ) : (
          <>
            <ImageUp size={18} className="text-mist-faint" strokeWidth={1.5} />
            <span className="text-[10px] text-mist-faint text-center px-2">
              Drop or click
            </span>
          </>
        )}
      </div>

      <input
        id={`channel-${channel}`}
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => accept(e.target.files?.[0])}
      />

      {file && (
        <p className="text-[10px] text-mist-faint mt-1.5 truncate" title={file.name}>
          {file.name} · {(file.size / 1024).toFixed(0)} KB
        </p>
      )}
    </div>
  );
}
