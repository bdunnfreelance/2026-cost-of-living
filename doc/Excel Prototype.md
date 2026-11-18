
# Excel Prototype

I set up a basic Cost of Living system in Excel to get some visibility into where our income and expenses are according to a set of categories. This doc describes the spreadsheet structure and logic. Use this as a specification for the first version of our Cost of Living app.

Here are the main working sheets. There are other sheets that are for separate but related activitis.

1. Transactions - contains all normalised transactions from all relevant bank accounts
2. Budget Categories - lists all the categories and category groups that we use to track income and expenses
3. Category Mapping - each line maps a transaction to a budget category. Use this for unusual one-off transactions.
4. Mapping Rules - each line contains a search string. Any transaction description that contains this string is mapped to a category
5. Cost of Living - contains pivot tables to summarise expenses by category and category group
6. Income - contains pivot tables to summarise income by category and category group


# Data Sheets

## Sheet - Transactions

All transactions downloaded from online banking have been normalised and loaded into this sheet. Here are the collumns and their purpose:

Table Name: Transaction

#### Raw Data Fields
Bank	    - name of the bank
Account	    - name of the account, e.g. Savings, Visa, Work
Date	    - date of the transaction
Mth/Yr	    - calculated field used to group transactions in a pivot table by year and month
Description	- transaction description
Debit 	    - transaction amount debited
Credit 	    - transaction amount credited
Balance	    - account balance where available (not sure if this is needed in most cases)
Category	- some banks provide a category
SubCategory	- some banks provide a subcategory

#### Calculated Fields
TranId	- calculated field used to uniquely identify a transaciton
    ```=[@Account]&"|"&TEXT([@Date],"yyyymmdd")&"|"&[@Description]```
DescId	- calculated field used to uniquely identify a description for mapping
    ```=[@Account]&"|"&[@Description]```

#### Debug Fields
Matching Rule	- show the name of the mapping rule if found
    ```
    =LET( m,
        XLOOKUP( [@Description], CategoryMap[Description], CategoryMap[Manual Category], "" ),
        IF( m="",
            XLOOKUP( TRUE, ISNUMBER(SEARCH(MappingRules[MatchText],[@Description])), "Rule: " & MappingRules[MatchText], "(Uncategorised)" ),
            "Exact Match" ))
    ```
Payment Category	- show the category using the Manual Category if found, then the Rule Base Category if foun
    ```
    =LET( m,
        XLOOKUP( [@Description], CategoryMap[Description], CategoryMap[Manual Category], "" ),
        IF( m="",
            XLOOKUP( TRUE, ISNUMBER(SEARCH(MappingRules[MatchText],[@Description])), MappingRules[Payment Category], "(Uncategorised)" ),
            m ) )
    ```
Manual Category	- test if each transaction maps to a Budget Category via the manual Category Mapping sheet
    ```=XLOOKUP( [@Description], CategoryMap[Description], CategoryMap[Manual Category], "" )```
Rule Based Category	- test if each transaction maps to a Budget Category via the Mapping Rules sheet
    ```=XLOOKUP( TRUE, ISNUMBER(SEARCH(MappingRules[MatchText],[@Description])), MappingRules[Payment Category], "" )```


## Sheet - Category Groups

Table Name: CategoryGroup

#### Raw Data Fields

Payment Category	- name of category
Category Group	    - higher level grouping
Cash Flow	        - type of category: Regular, One-off, Transfer, Unused
Comment             - free text comment field

#### Calculated Fields

#### Debug Fields

Times Used in Mapping	- count number of times this category is used in the manual mapping table
    ```=COUNTIF('Category Mapping - All'!D:D,[@[Payment Category]])```
Amount in Category	    - Show total Debits mapped to this category
    ```=SUMIF('Category Mapping - All'!D:D,[@[Payment Category]],'Category Mapping - All'!G:G)```
Times Used in Rules	    - count number of times this category is used in the mapping rule table
    ```=COUNTIF('Mapping Rules'!C:C,[@[Payment Category]])```


## Sheet - Category Mapping

Each line maps a transaction to a budget category. Use this for unusual one-off transactions.

Note: there are some debug columns to determine if a manual mapping can be deleted in favour of a mapping rule.

Table Name: CategoryMap

#### Raw Data Fields

Account	        - account namee
Description	    - full description from the Transactions table
Manual Category	- category name

#### Calculated Fields

DescId	- used to map to a transaction deescription
    ```=[@Account]&"|"&[@Description]```

#### Debug Fields

Occurances  - nummber of transactions mapped with this description (can be more than one)
    ```=COUNTIF(Transactions!G:G,[@Description])```

1st Date	- date of earliest transaction that uses this map
    ```=XLOOKUP([@Description],Transactions!G:G,Transactions!E:E,"(None)",1)```

Total Debits	- total that use this map
    ```=SUMIF(Transactions!G:G,[@Description],Transactions!H:H)```

Total Credits	- total that use this map
    ```=SUMIF(Transactions!G:G,[@Description],Transactions!I:I)```

Match Text	    - match text is mapping rule is used
    ```=XLOOKUP( TRUE, ISNUMBER(SEARCH(MappingRules[MatchText],[@Description])), MappingRules[MatchText], "" )```

Rule Based Category	- cateogry if the mapping rules are used
    ```=XLOOKUP( TRUE, ISNUMBER(SEARCH(MappingRules[MatchText],[@Description])), MappingRules[Payment Category], "" )```

Category Comparison - would a mapping rule give the same or different result
    ```
    = IF( [@[Rule Based Category]]="", "Blank Rule",
        IF( [@[Manual Category]]=[@[Rule Based Category]],"Same",
            IF([@[Manual Category]]="","Manual Blank","Different") ) )
    ```


## Sheet - Mapping Rules

Each line contains a search string. Any transaction description that contains this string is mapped to a category.

Rule priority is:
a. Rule Type: Specific Payees first, then generic Vendor Types
b. Row order

Table Name: MappingRules

#### Raw Data Fields

Rule Type           - 1. Payee (e.g. 'OFFICEWORKS'), 2. Vendor Type (e.g. 'HARDWARE')
MatchText	        - text to search for in a transaction description
Payment Category	- category to map to
Comment             - free text comment

#### Calculated Fields

#### Debug Fields

Cat Grp Check	    - Check whether there is a category available for this rule
    ```=VLOOKUP([@[Payment Category]],'Budget Categories'!A:B,2,FALSE)```

Times Used	        - number of times this rule is used
    ```=SUMPRODUCT( --ISNUMBER( SEARCH( [@MatchText], Transaction[Description] ) ) )```


# Data Tables and Joins

Transaction t

CategoryMap m
    - joins to Transaction on DescId

MappingRules r
    - joins to Transaction where MatchText is found in the Transaction Description

CategoryGroup c
    - joins to CategoryMap m on c.Payment Category = m.Manual Category
    - joins to MappingRules r on c.Payment Category = r.Payment Category


# Presentation Sheets

## Sheet - Cost of Living

### Pivot Table - Yearly Debits for Regular Cash Flow

#### Filters
Category Group.Cash Flow = Regular
Transaction.Date(Month)

#### Columns
Transaction.Date(Year)

#### Rows
Category Group.Category Group
Category Group.Paymant Category
Transaction.Account
Transaction.Description

#### Values
Sum of Transaction.Debit


### Pivot Table - Monthly Debits in 2026 for Regular Cash Flow

#### Filters
Category Group.Cash Flow = Regular
Transaction.Date(Year)

#### Columns
Transaction.Date(Month)

#### Rows
Category Group.Category Group
Category Group.Paymant Category
Transaction.Account
Transaction.Description

#### Values
Sum of Transaction.Debit



## Sheet - Income

### Pivot Table - Yearly Credits for Regular Cash Flow

#### Filters
Category Group.Cash Flow = Regular
Transaction.Date(Month)

#### Columns
Transaction.Date(Year)

#### Rows
Category Group.Category Group
Category Group.Paymant Category
Transaction.Account
Transaction.Description

#### Values
Sum of Transaction.Credit


### Pivot Table - Monthly Credits in 2026 for Regular Cash Flow

#### Filters
Category Group.Cash Flow = Regular
Transaction.Date(Year)

#### Columns
Transaction.Date(Month)

#### Rows
Category Group.Category Group
Category Group.Paymant Category
Transaction.Account
Transaction.Description

#### Values
Sum of Transaction.Credit


# DuckDB + Power BI Implementation

The goal of this project is to replicate the Excel charts in Power BI with a more robust data store. Since Power BI does not natively load DuckDB database files, the decision was made to export the data into a parquet file ready for a simple load into Power BI.

To achieve this, create one enriched transaction view and load one table directly into Power BI. Its 18 fields are Bank, Account, Date, Description, Debit, Credit, Balance, Category, SubCategory, TranId, DescId, Matching Rule, Payment Category, Manual Category, Rule Based Category, Category Group, Cash Flow, and Comment. Omit `Mth/Yr`; Power BI can group the Date field directly.

Payment Category is the effective category: first use the manual mapping joined by `Account|Description`; if no manual category exists, use the first matching description rule, ordered by Payee before Vendor Type and then by rule row order. Join Category Group, Cash Flow, and Comment from `CategoryGroup` where `CategoryGroup[Payment Category]` equals the effective transaction Payment Category. These are many-to-one lookups, so the result remains one row per transaction. If Payment Category is blank, the category metadata is blank.

