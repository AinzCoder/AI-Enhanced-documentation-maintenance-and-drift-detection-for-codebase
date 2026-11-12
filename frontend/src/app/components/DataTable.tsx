
import type { ReactNode } from "react";

export interface TableColumn<T> {
  header: string;
  render: (row: T) => ReactNode;
}

interface DataTableProps<T> {
  columns: TableColumn<T>[];
  data: T[];
  getRowKey: (row: T) => string;
  emptyMessage?: string;
}

export default function DataTable<T>({
  columns,
  data,
  getRowKey,
  emptyMessage = "No records found.",
}: DataTableProps<T>) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800">
      <table className="w-full min-w-[600px] text-left text-sm">
        <thead className="bg-[#111B2E] text-slate-400">
          <tr>
            {columns.map((column, index) => (
              <th
                key={index}
                className="px-5 py-4 font-semibold"
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>

        <tbody className="divide-y divide-slate-800 bg-[#151F33]">
          {data.length > 0 ? (
            data.map((row) => (
              <tr
                key={getRowKey(row)}
                className="transition hover:bg-slate-800/50"
              >
                {columns.map((column, index) => (
                  <td
                    key={index}
                    className="px-5 py-4 text-slate-300"
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td
                colSpan={columns.length}
                className="px-5 py-10 text-center text-slate-500"
              >
                {emptyMessage}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
