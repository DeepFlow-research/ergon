"use client";

/**
 * CSV viewer. Parses the whole buffer with papaparse and renders up to
 * CSV_ROW_CAP rows in a sticky-header table. Beyond the cap we surface a
 * warning banner and truncate — the modal isn't meant to be a spreadsheet.
 */

import { useMemo } from "react";
import Papa, { type ParseResult } from "papaparse";

const CSV_ROW_CAP = 500;

interface CsvViewerProps {
  text: string;
}

export function CsvViewer({ text }: CsvViewerProps) {
  const parsed = useMemo<ParseResult<Record<string, string>>>(
    () => Papa.parse<Record<string, string>>(text, { header: true, skipEmptyLines: true }),
    [text],
  );

  const rows = parsed.data;
  const headers = parsed.meta.fields ?? (rows[0] ? Object.keys(rows[0]) : []);
  const truncated = rows.length > CSV_ROW_CAP;
  const visible = truncated ? rows.slice(0, CSV_ROW_CAP) : rows;

  if (headers.length === 0) {
    return <div className="p-6 text-sm text-gray-500 dark:text-gray-400">Empty CSV.</div>;
  }

  return (
    <div className="flex h-full flex-col">
      {truncated ? (
        <div className="border-b border-amber-200 bg-amber-50 px-5 py-2 text-xs text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200">
          Showing the first {CSV_ROW_CAP.toLocaleString()} of {rows.length.toLocaleString()} rows.
        </div>
      ) : null}
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="min-w-full divide-y divide-gray-200 font-mono text-xs dark:divide-gray-800">
          <thead className="sticky top-0 bg-gray-50 dark:bg-gray-900">
            <tr>
              {headers.map((h) => (
                <th
                  key={h}
                  className="whitespace-nowrap px-3 py-2 text-left font-semibold text-gray-700 dark:text-gray-200"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {visible.map((row, idx) => (
              <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                {headers.map((h) => (
                  <td key={h} className="whitespace-pre-wrap px-3 py-1.5 text-gray-800 dark:text-gray-100">
                    {row[h] ?? ""}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
