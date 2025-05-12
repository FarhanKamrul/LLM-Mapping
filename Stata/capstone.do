/*
Regression Discontinuity Design Analysis of ChatGPT's Effect on Citation Counts
*/

ssc install reghdfe, replace
ssc install ftools, replace
ssc install ivreg2, replace
ssc install ranktest, replace

* Import the CSV file
import delimited "C:\Users\Farhan\Desktop\Sem 8\Capstone\Code\Fresh\stata_prep\chatgpt_citation_analysis.csv", clear


* Convert publication_date string to Stata date
gen pub_date = date(publication_date, "YMD")
format pub_date %td

* Drop articles outside desired date range
drop if pub_date < td(01jan2021) | pub_date > td(31jan2025)

* Define cutoff: Nov 22, 2022 =  22nov2022
gen post_gpt_cutoff = pub_date >= td(22nov2022)
label define gptlbl 0 "Pre-GPT" 1 "Post-GPT"
label values post_gpt_cutoff gptlbl




// authorship by hemispheric region count
tab auth_region_h


// authorship by ontinental region count 
tab auth_region_c


// pre-post count bar	
tab post_gpt_cutoff




// Encode string variables
encode type, gen(type_enc)
encode sjrbestquartile, gen(sjrbestquartile_enc)
encode auth_region_c, gen(auth_region_c_enc)
encode source_clean, gen(source_enc)
drop if missing(sjrbestquartile_enc)




*--- (a) category_main  → numeric with value labels
capture confirm string variable category_main
if _rc==0 {
    encode category_main, gen(cat_main) label(cat_main_lbl)
    label var cat_main "Category (numeric)"
}

*--- (b) SJR Best Quartile  (values like "Q1","Q2"…)  → 1,2,3,4
capture confirm string variable sjrbestquartile
if _rc==0 {
    gen byte sjr_q = real(substr(lower(sjrbestquartile), 2, .))
    label define sjr_q_lbl 1 "Q1" 2 "Q2" 3 "Q3" 4 "Q4"
    label values sjr_q sjr_q_lbl
    label var sjr_q "SJR best quartile (1=Q1 … 4=Q4)"
}

*--- (c) publication_country  → numeric code
capture confirm string variable publication_country
if _rc==0 {
    encode publication_country, gen(pub_ctry) label(pub_ctry_lbl)
    label var pub_ctry "Publication country (numeric)"
}

*--- (d) days_from_cutoff   (already numeric) – keep as-is
label var days_from_cutoff "Days from ChatGPT cutoff"

*--- (e) from_east  (already 0/1) – ensure type is byte
recast byte from_east
label define bloc_lbl 0 "Global West" 1 "Global East"
label values from_east bloc_lbl
label var from_east "Author bloc (dummy)"

*--- (f) hindex  (numeric) – keep but rename if desired
label var hindex "Journal H-index"


// Step 1: Convert publication date
gen pub_date = date(publication_date, "YMD")
format pub_date %td

// Step 2: Set a fixed reference date (Jan 2025)
gen today = td(31jan2025)
format today %td

// Step 3: Compute age in years
gen age_days = today - pub_date
gen age_years = age_days / 365.25

// Step 4: Compute the exposure score using standard normal CDF
gen exposure_score = normal((age_years - 2.5) / 1)
label variable exposure_score "Citation Exposure Score"

drop auth_region_c

rename auth_region_h auth_hemisphere
encode auth_hemisphere, gen(auth_hemisphere_enc)
drop auth_hemisphere
rename auth_hemisphere_enc auth_hemisphere
rename auth_region_c_enc auth_continent


* Re‐define gpt_wave with correct cut-offs
drop gpt_wave
gen byte gpt_wave = .

* Exact release dates
local d35 = date("2022-11-23","YMD")    // GPT-3.5
local d4  = date("2023-03-14","YMD")    // GPT-4
local d4o = date("2023-07-24","YMD")    // GPT-4o
local d4om= date("2024-01-10","YMD")    // GPT-4o-mini

replace gpt_wave = 0 if pub_date < `d35'
replace gpt_wave = 1 if inrange(pub_date, `d35', `d4'  - 1)
replace gpt_wave = 2 if inrange(pub_date, `d4',  `d4o' - 1)
replace gpt_wave = 3 if inrange(pub_date, `d4o', `d4om'- 1)
replace gpt_wave = 4 if pub_date >= `d4om'

label define gptwave 0 "Pre-GPT" ///
                     1 "Post-GPT3.5" ///
                     2 "Post-GPT4" ///
                     3 "Post-GPT4o" ///
                     4 "Post-GPT4o-mini"
label values gpt_wave gptwave

tabulate gpt_wave, missing

* Collapse Africa/Middle East into Middle East
recode auth_continent (2=6)

* Verify
tabulate auth_continent



// RQ 1==========================================================
// STUDY 1: ADOPTION

regress binoculars_score ///
    i.post_chatgpt##i.auth_hemisphere ///
    i.sjr_q hindex, vce(robust)

regress binoculars_score ///
    i.post_chatgpt##i.auth_continent ///
    i.sjr_q hindex, vce(robust)
	
logit accuracy_prediction ///
    i.post_chatgpt##i.auth_hemisphere ///
    i.sjr_q hindex, vce(robust)

logit accuracy_prediction ///
    i.post_chatgpt##i.auth_continent ///
    i.sjr_q hindex, vce(robust)

	


// STUDY 2: PER MODEL ANALYSIS
regress binoculars_score ///
    i.gpt_wave##i.from_east ///
    i.sjr_q hindex, vce(robust)

logit accuracy_prediction ///
    i.gpt_wave i.sjr_q hindex i.from_east, vce(robust)




// RQ 2======================================================
// STUDY 1: Citation Rates
zinb cited_by_count ///
    c.binoculars_score##i.post_gpt##i.auth_hemisphere ///
    hindex i.sjr_q exposure_score, ///
    inflate(binoculars_score hindex exposure_score i.sjr_q) ///
    vce(robust)

zinb cite_diff_region_h ///
    c.binoculars_score##i.post_gpt##i.auth_hemisphere ///
    hindex i.sjr_q exposure_score, ///
    inflate(binoculars_score hindex exposure_score i.sjr_q) ///
    vce(robust)


	
