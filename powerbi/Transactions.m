let
    // Update ProjectRoot once if this project is stored in a different folder.
    ProjectRoot = "C:\\Dev\\2026 CostOfLiving",
    Source = Parquet.Document(
        File.Contents(ProjectRoot & "\\data\\3. load\\transactions.parquet")
    ),
    Typed = Table.TransformColumnTypes(
        Source,
        {
            {"Bank", type text},
            {"Account", type text},
            {"Date", type date},
            {"Description", type text},
            {"Debit", Currency.Type},
            {"Credit", Currency.Type},
            {"Balance", Currency.Type},
            {"Category", type text},
            {"SubCategory", type text},
            {"TranId", type text},
            {"DescId", type text},
            {"Matching Rule", type text},
            {"Payment Category", type text},
            {"Manual Category", type text},
            {"Rule Based Category", type text},
            {"Category Group", type text},
            {"Cash Flow", type text},
            {"Comment", type text},
            {"Data Status", type text}
        }
    )
in
    Typed
