/** A plain table for columns + row arrays (used for query previews and data). */
export function DataTable({
  columns,
  rows,
  maxRows,
}: {
  columns: string[];
  rows: unknown[][];
  maxRows?: number;
}) {
  const shown = maxRows ? rows.slice(0, maxRows) : rows;
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j}>{cell === null || cell === undefined ? "—" : String(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {maxRows && rows.length > maxRows && (
        <div className="subtle" style={{ padding: "8px 12px" }}>
          … {rows.length - maxRows} more rows
        </div>
      )}
    </div>
  );
}
