-- Safety net. {{< ex Ex#PY-0001 >}} markers are expanded into real
-- {pyodide} cells by tools/expand-exercises.py at pre-render, because
-- quarto-live's live.lua filter runs before custom shortcodes and would
-- otherwise leave a static <pre class="pyodide">. If this handler still
-- runs, a marker was missed — fail the render rather than silently
-- degrade the cell.
return {
  ["ex"] = function(args, kwargs, meta)
    local id = "unknown"
    if args and #args > 0 then
      id = pandoc.utils.stringify(args[1])
    end
    error("ex shortcode '" .. id .. "' was not expanded at pre-render; quarto-live cells must exist at parse time")
  end,
}
