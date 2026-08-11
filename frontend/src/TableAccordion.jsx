import { useState } from 'react'

const ROWS = 10

const emptyRows = (n = ROWS) => Array.from({ length: n }, () => ({ a: '', b: '' }))

/**
 * One collapsible section containing an editable two-column table.
 *
 *   <TableAccordion
 *     title="Sound speed profile"
 *     columns={['Depth (m)', 'Speed (m/s)']}
 *     onChange={(rows) => ...}
 *   />
 *
 * Starts closed with 10 blank rows. Each cell is a text input; every row has a
 * delete button, and "Add row" appends one.
 */
export default function TableAccordion({
  title = 'Values',
  columns = ['Depth (m)', 'Temperature (°C)'],
  onChange,
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [rows, setRows] = useState(emptyRows)

  function commit(next) {
    setRows(next)
    onChange?.(next)
  }

  const setCell = (index, key, value) =>
    commit(rows.map((row, i) => (i === index ? { ...row, [key]: value } : row)))

  const addRow = () => commit([...rows, { a: '', b: '' }])

  const deleteRow = (index) => commit(rows.filter((_, i) => i !== index))

  return (
    <section className="acc">
      <button
        type="button"
        className="acc-header"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(!isOpen)}
      >
        {title}
        <span aria-hidden="true">{isOpen ? '−' : '+'}</span>
      </button>

      {isOpen && (
        <div className="acc-body">
          <table className="acc-table">
            <thead>
              <tr>
                <th>{columns[0]}</th>
                <th>{columns[1]}</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                // Rows have no stable id, so the index is the key. Fine here
                // because rows are only appended or removed, never reordered.
                <tr key={index}>
                  <td>
                    <input
                      value={row.a}
                      aria-label={`${columns[0]} row ${index + 1}`}
                      onChange={(e) => setCell(index, 'a', e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      value={row.b}
                      aria-label={`${columns[1]} row ${index + 1}`}
                      onChange={(e) => setCell(index, 'b', e.target.value)}
                    />
                  </td>
                  <td>
                    <button
                      type="button"
                      className="acc-delete"
                      aria-label={`Delete row ${index + 1}`}
                      onClick={() => deleteRow(index)}
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <button type="button" className="acc-add" onClick={addRow}>
            + Add row
          </button>
        </div>
      )}
    </section>
  )
}
