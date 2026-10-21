import { useEffect, useState } from 'react'


const ROWS = 8

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

  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContents, setFileContents] = useState("");

  const onFileChange = async (event) => {
    const file = event.target.files[0];

    if (!file) return;

    setSelectedFile(file);

    let readInputFile = await inputFileReader(event);

    setFileContents(readInputFile);
  }

  function inputFileReader(event) {
    return new Promise((res,rej)=>{
      let input = event.target;
      let reader = new FileReader();
      reader.onload = function(){
        res(reader.result)
      };
      reader.readAsText(input.files[0]);
    });
  }

  /** Real casts come with a metadata preamble (ship, station, coefficients,
   * unit labels) instead of a fixed header line, so there is no reliable
   * marker for "data starts here". Keep only the lines where both columns
   * are actually numeric -- that skips the preamble, any header/units row,
   * and blank lines, regardless of what the file's header actually says. */
  function parseFileContents() {
    const contents = fileContents;
    if (!contents) return [];
    const lines = contents.split('\n');
    const parsedRows = lines
      .map(line => {
        const [depth, temperature] = line.split(',');
        return { a: (depth ?? '').trim(), b: (temperature ?? '').trim() };
      })
      .filter(
        (row) =>
          row.a !== '' &&
          row.b !== '' &&
          Number.isFinite(Number(row.a)) &&
          Number.isFinite(Number(row.b)),
      );
    return parsedRows;
  }

  // Whenever the file contents change, parse them and update the rows.
  useEffect(() => {
    if (fileContents) {
      const parsedRows = parseFileContents();
      commit(parsedRows);
    }
  }, [fileContents]);

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
          <div className="acc-table-scroll">
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
                  // Rows have no stable id, so the index is the key
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
          </div>

          <button type="button" className="acc-add" onClick={addRow}>
            + Add row
          </button>
          <input type="file" onChange={onFileChange} />

          {selectedFile && (
            <>
              <p>File: {selectedFile.name}</p>

              <h3>Contents</h3>
              <pre className="acc-file-contents">{fileContents}</pre>
            </>
          )}
        </div>
      )}
    </section>
  )
}
