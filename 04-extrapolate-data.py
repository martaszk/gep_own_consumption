"""
Purpose:
Build the country-year extrapolation panel for own consumption values.

What this script now does:
1) Loads eligible LMIC country-year panel and merges observed/interpolated own consumption.
2) Adds country-year covariates from local intermediates.
3) Tries to download additional FAOSTAT domain regressors using Python package `faostat`.
4) Ranks FAOSTAT-related features by simple Pearson correlation with observed own consumption.
5) Evaluates one-feature linear regressions out-of-sample using country-group folds.
6) Uses the strongest-correlation feature for extrapolation.
7) Exports the extrapolated panel and a report-ready correlation/regression table.

Notes:
- FAOSTAT API requires authentication. Set one of:
  - FAOSTAT_TOKEN
  - OR FAOSTAT_USERNAME and FAOSTAT_PASSWORD
- If FAOSTAT credentials are not available, the script runs with local covariates only.
"""

import os
import re
import unicodedata
import numpy as np
import pandas as pd


def limit_years(data):
    year_columns = [col for col in data.columns if col.isdigit() and 2004 <= int(col) <= 2021]
    return year_columns


def normalize_country_name(name):
    if pd.isna(name):
        return ""
    normalized = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().strip().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


COUNTRY_ALIASES = {
    "United Republic of Tanzania": "Tanzania, United Republic of",
}


def add_iso_codes(df):
    iso = pd.read_csv("input/ISO-3-codes.csv", delimiter=",", encoding="utf-8")
    iso = iso[["name", "alpha-3"]].copy()
    iso["country_key"] = iso["name"].apply(normalize_country_name)

    out = df.copy()
    out["country_iso_name"] = out["Country"].replace(COUNTRY_ALIASES)
    out["country_key"] = out["country_iso_name"].apply(normalize_country_name)
    out = pd.merge(out, iso[["country_key", "alpha-3"]], on="country_key", how="left", suffixes=("", "_iso"))

    if "alpha-3_iso" in out.columns:
        if "alpha-3" in out.columns:
            out["alpha-3"] = out["alpha-3"].combine_first(out["alpha-3_iso"])
        else:
            out["alpha-3"] = out["alpha-3_iso"]
        out = out.drop(columns=["alpha-3_iso"])

    out = out.drop(columns=["country_iso_name", "country_key"])
    return out


def prepare_base_panel():
    df_cntry = pd.read_csv("./input/WBHIST.csv", delimiter=";", encoding="utf-8")
    year_columns = limit_years(df_cntry)
    df_cntry = df_cntry[["Country"] + year_columns]
    df_cntry = df_cntry.melt(id_vars=["Country"], var_name="Year", value_name="wb_income")

    cond = (df_cntry["wb_income"] == "L") | (df_cntry["wb_income"] == "LM")
    df_cntry = df_cntry[cond].copy()
    df_cntry["Year"] = df_cntry["Year"].astype(int)

    df_int = pd.read_csv("./intermediates/data-own-consumption-interpolation-ISO.csv", delimiter=",", encoding="utf-8")
    df_covar = pd.read_csv("./intermediates/data-covariates.csv", delimiter=",", encoding="utf-8")
    df_covar = df_covar.rename(columns={"name": "Country"})

    # Keep one row per country-year in covariates (there may be duplicates from FAO item/element granularity).
    covar_numeric = [
        "GDP_capita",
        "Value",
        "cropland_ha_1000",
        "agricultural_land_ha_1000",
        "ag_value_per_area_int_usd",
        "smallholder_lt2ha_share_pct",
        "is_low_income",
        "is_lower_middle_income",
    ]
    existing_numeric = [c for c in covar_numeric if c in df_covar.columns]
    agg_dict = {c: "mean" for c in existing_numeric}
    df_covar_small = (
        df_covar[["Country", "Year"] + existing_numeric]
        .groupby(["Country", "Year"], as_index=False)
        .agg(agg_dict)
    )

    df_merge = pd.merge(df_cntry, df_int, on=["Year", "Country"], how="left")
    df_merge = pd.merge(df_merge, df_covar_small, on=["Country", "Year"], how="left")
    df_merge = add_iso_codes(df_merge)
    return df_merge


def _safe_import_faostat():
    try:
        import faostat
        return faostat
    except Exception:
        return None


def _configure_faostat_auth(faostat_module):
    token = os.getenv("FAOSTAT_TOKEN")
    username = os.getenv("FAOSTAT_USERNAME")
    password = os.getenv("FAOSTAT_PASSWORD")

    if token:
        faostat_module.set_requests_args(token=token, timeout=45.0)
        return True, "token"

    if username and password:
        faostat_module.set_requests_args(username=username, password=password, timeout=45.0)
        return True, "username_password"

    return False, "missing_credentials"


def _find_domain_code(ds_df, keywords):
    labels = ds_df.copy()
    labels["_label"] = labels["label"].astype(str).str.lower()
    for kw in keywords:
        hits = labels[labels["_label"].str.contains(kw, na=False)]
        if not hits.empty:
            return hits.iloc[0]["code"], hits.iloc[0]["label"]
    return None, None


def _extract_area_year_value_columns(df):
    area_candidates = ["Area", "area", "Area Label"]
    year_candidates = ["Year", "year"]
    value_candidates = ["Value", "value"]
    area_code_candidates = ["Area Code", "Area code", "Area Code (M49)"]

    area_col = next((c for c in area_candidates if c in df.columns), None)
    year_col = next((c for c in year_candidates if c in df.columns), None)
    value_col = next((c for c in value_candidates if c in df.columns), None)
    area_code_col = next((c for c in area_code_candidates if c in df.columns), None)

    return area_col, year_col, value_col, area_code_col


def _download_domain_aggregate(faostat_module, domain_code, country_names, years, category_name):
    # Build pars dynamically from available domain parameters.
    pars_info = faostat_module.list_pars_df(domain_code)
    par_codes = set(pars_info["parameter code"].astype(str).str.lower().tolist())

    pars = {}
    if "year" in par_codes:
        pars["year"] = list(map(int, sorted(set(years))))

    if "area" in par_codes:
        try:
            area_dict = faostat_module.get_par(domain_code, "area")
            area_lookup = {normalize_country_name(lbl): code for lbl, code in area_dict.items()}
            selected_area_codes = []
            for c in country_names:
                key = normalize_country_name(c)
                if key in area_lookup:
                    selected_area_codes.append(area_lookup[key])
            if selected_area_codes:
                pars["area"] = selected_area_codes
            else:
                # Without area filters, API calls become too large and can hang.
                return pd.DataFrame(columns=["alpha-3", "Year", f"faostat_{category_name}_mean"])
        except Exception:
            return pd.DataFrame(columns=["alpha-3", "Year", f"faostat_{category_name}_mean"])

    # Reduce query size by selecting a compact subset of elements/items.
    subset_keywords = {
        "production": ["gross production value", "production value", "value"],
        "food_security": ["prevalence", "food insecurity", "undernourishment"],
        "food_balance": ["food supply", "kcal", "protein", "fat"],
        "consumer_price_index": ["consumer price", "index", "inflation"],
        "diet_affordability": ["cost", "afford", "diet"],
        "sustainability": ["emissions", "sustainability", "intensity"],
        "rural_employment": ["employment", "labor", "labour", "rural"],
    }

    def _select_codes(par_name):
        if par_name not in par_codes:
            return None
        try:
            values = faostat_module.get_par(domain_code, par_name)
            keys = subset_keywords.get(category_name, [])
            picked = []
            for label, code in values.items():
                ll = str(label).lower()
                if any(k in ll for k in keys):
                    picked.append(code)
                if len(picked) >= 5:
                    break
            if picked:
                return picked
        except Exception:
            return None
        return None

    element_codes = _select_codes("element")
    if element_codes:
        pars["element"] = element_codes

    item_codes = _select_codes("item")
    if item_codes:
        pars["item"] = item_codes

    coding = {"area": "ISO3"} if "area" in par_codes else {}

    data = faostat_module.get_data_df(
        domain_code,
        pars=pars,
        coding=coding,
        strval=False,
        limit=20000,
    )

    if data is None or len(data) == 0:
        return pd.DataFrame(columns=["alpha-3", "Year", f"faostat_{category_name}_mean"])

    area_col, year_col, value_col, area_code_col = _extract_area_year_value_columns(data)
    if year_col is None or value_col is None:
        return pd.DataFrame(columns=["alpha-3", "Year", f"faostat_{category_name}_mean"])

    out = data.copy()
    out[value_col] = pd.to_numeric(out[value_col], errors="coerce")
    out[year_col] = pd.to_numeric(out[year_col], errors="coerce")

    if area_code_col is not None:
        out["alpha-3"] = out[area_code_col].astype(str).str.upper().str.strip()
        out["alpha-3"] = out["alpha-3"].where(out["alpha-3"].str.len() == 3)
    elif area_col is not None:
        out["Country"] = out[area_col]
        out = add_iso_codes(out)
    else:
        return pd.DataFrame(columns=["alpha-3", "Year", f"faostat_{category_name}_mean"])

    out = out.rename(columns={year_col: "Year", value_col: "_value"})
    out = out[["alpha-3", "Year", "_value"]].dropna(subset=["alpha-3", "Year", "_value"])
    out["Year"] = out["Year"].astype(int)

    # Aggregate domain data to country-year regressor.
    out = out.groupby(["alpha-3", "Year"], as_index=False)["_value"].mean()
    out = out.rename(columns={"_value": f"faostat_{category_name}_mean"})
    return out


def fetch_faostat_regressors(df_base):
    faostat_module = _safe_import_faostat()
    if faostat_module is None:
        print("faostat package not installed; proceeding with local covariates only.")
        return pd.DataFrame(columns=["alpha-3", "Year"])

    auth_ok, auth_method = _configure_faostat_auth(faostat_module)
    if not auth_ok:
        print("FAOSTAT credentials not found in environment; proceeding with local covariates only.")
        return pd.DataFrame(columns=["alpha-3", "Year"])

    print(f"FAOSTAT authentication configured via: {auth_method}")

    # Live FAOSTAT pulls can be very heavy; gate them behind an explicit switch.
    # Set FAOSTAT_PULL_DATA=1 to enable full API feature download.
    if os.getenv("FAOSTAT_PULL_DATA", "0") != "1":
        print("FAOSTAT data pull disabled (set FAOSTAT_PULL_DATA=1 to enable API regressor download).")
        return pd.DataFrame(columns=["alpha-3", "Year"])

    try:
        ds = faostat_module.list_datasets_df()
    except Exception as err:
        print(f"Unable to retrieve FAOSTAT datasets: {err}")
        return pd.DataFrame(columns=["alpha-3", "Year"])

    domain_keywords = {
        "food_security": ["food security"],
        "food_balance": ["food balances", "supply utilization"],
        "consumer_price_index": ["consumer price", "price index"],
        "diet_affordability": ["affordability", "healthy diet", "cost"],
        "sustainability": ["sustainability", "environment", "emissions"],
        "rural_employment": ["employment", "labour", "labor", "rural"],
    }

    countries = sorted(df_base["Country"].dropna().unique().tolist())
    years = sorted(df_base["Year"].dropna().astype(int).unique().tolist())

    outputs = []
    for category, keywords in domain_keywords.items():
        code, label = _find_domain_code(ds, keywords)
        if code is None:
            print(f"No FAOSTAT domain found for category '{category}'.")
            continue

        if code == "QV":
            print("Skipping heavy FAOSTAT domain QV to avoid long-running download.")
            continue

        print(f"Downloading FAOSTAT category '{category}' from domain {code} ({label})")
        try:
            cat_df = _download_domain_aggregate(faostat_module, code, countries, years, category)
            outputs.append(cat_df)
        except Exception as err:
            print(f"Failed FAOSTAT download for category '{category}' (domain {code}): {err}")

    if not outputs:
        return pd.DataFrame(columns=["alpha-3", "Year"])

    feat = outputs[0]
    for chunk in outputs[1:]:
        feat = pd.merge(feat, chunk, on=["alpha-3", "Year"], how="outer")

    return feat


def _fit_simple_linear(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 2:
        return None, None
    if np.nanstd(x) == 0:
        return None, None
    slope, intercept = np.polyfit(x, y, deg=1)
    return float(intercept), float(slope)


def _r2_score(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if len(y_true) == 0:
        return np.nan
    denom = np.sum((y_true - np.mean(y_true)) ** 2)
    if denom == 0:
        return np.nan
    num = np.sum((y_true - y_pred) ** 2)
    return float(1 - num / denom)


def _country_group_folds(countries, max_folds=5):
    groups = sorted(pd.Series(countries).dropna().unique().tolist())
    if len(groups) < 2:
        return []
    k = min(max_folds, len(groups))
    folds = []
    for i in range(k):
        folds.append(set(groups[i::k]))
    return folds


def build_correlation_regression_table(df, feature_cols, target_col="own_con2"):
    train_df = df[df[target_col].notna()].copy()
    train_df = train_df.dropna(subset=["Country"]).copy()

    if len(train_df) < 20:
        raise ValueError("Not enough training rows to evaluate correlation regressions.")

    feature_cols = [c for c in feature_cols if train_df[c].notna().any()]
    if len(feature_cols) == 0:
        raise ValueError("No non-missing FAOSTAT feature columns available for correlation regressions.")

    rows = []
    for feature in feature_cols:
        sub = train_df[["Country", feature, target_col]].dropna().copy()
        n_pairs = len(sub)
        if n_pairs < 20:
            continue

        pearson_r = sub[feature].corr(sub[target_col])
        if pd.isna(pearson_r):
            continue

        intercept, slope = _fit_simple_linear(sub[feature].values, sub[target_col].values)
        if intercept is None or slope is None:
            continue

        folds = _country_group_folds(sub["Country"].values, max_folds=5)
        fold_rmse = []
        fold_mae = []
        fold_r2 = []

        if folds:
            for test_groups in folds:
                train_fold = sub[~sub["Country"].isin(test_groups)].copy()
                test_fold = sub[sub["Country"].isin(test_groups)].copy()

                if len(train_fold) < 2 or len(test_fold) == 0:
                    continue

                fold_intercept, fold_slope = _fit_simple_linear(
                    train_fold[feature].values,
                    train_fold[target_col].values,
                )
                if fold_intercept is None or fold_slope is None:
                    continue

                y_true = test_fold[target_col].values
                y_pred = np.clip(fold_intercept + fold_slope * test_fold[feature].values, a_min=0, a_max=None)

                fold_rmse.append(float(np.sqrt(np.mean((y_true - y_pred) ** 2))))
                fold_mae.append(float(np.mean(np.abs(y_true - y_pred))))
                fold_r2.append(_r2_score(y_true, y_pred))
        else:
            # Single-country fallback: report in-sample fit statistics.
            y_true = sub[target_col].values
            y_pred = np.clip(intercept + slope * sub[feature].values, a_min=0, a_max=None)
            fold_rmse.append(float(np.sqrt(np.mean((y_true - y_pred) ** 2))))
            fold_mae.append(float(np.mean(np.abs(y_true - y_pred))))
            fold_r2.append(_r2_score(y_true, y_pred))

        if len(fold_rmse) == 0:
            continue

        rows.append(
            {
                "feature": feature,
                "pearson_r": float(pearson_r),
                "abs_pearson_r": float(abs(pearson_r)),
                "slope": float(slope),
                "intercept": float(intercept),
                "cv_rmse_mean": float(np.mean(fold_rmse)),
                "cv_rmse_std": float(np.std(fold_rmse)),
                "cv_mae_mean": float(np.mean(fold_mae)),
                "cv_r2_mean": float(np.mean(fold_r2)),
                "n_train_rows": int(n_pairs),
            }
        )

    if len(rows) == 0:
        raise ValueError("No valid FAOSTAT feature had enough non-missing observations for regression.")

    perf = pd.DataFrame(rows).sort_values(["abs_pearson_r", "cv_rmse_mean"], ascending=[False, True]).reset_index(drop=True)
    perf["rank"] = np.arange(1, len(perf) + 1)
    return perf


def render_markdown_table(df, out_path):
    cols = [
        "rank",
        "feature",
        "pearson_r",
        "cv_rmse_mean",
        "cv_mae_mean",
        "cv_r2_mean",
        "n_train_rows",
    ]
    table = df[cols].copy()

    for c in ["pearson_r", "cv_rmse_mean", "cv_mae_mean", "cv_r2_mean"]:
        table[c] = table[c].map(lambda x: f"{x:,.4f}")

    header = "| " + " | ".join(cols) + " |\n"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |\n"
    rows = ""
    for _, row in table.iterrows():
        rows += "| " + " | ".join([str(row[c]) for c in cols]) + " |\n"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header + sep + rows)


def main():
    os.makedirs("results", exist_ok=True)

    df = prepare_base_panel()
    fao_feat = fetch_faostat_regressors(df)
    if not fao_feat.empty:
        df = pd.merge(df, fao_feat, on=["alpha-3", "Year"], how="left")

    # Keep a snapshot of original non-null status to label data source after filling.
    original_has_own_con = df["own_con"].notna()
    original_has_own_con2 = df["own_con2"].notna()

    candidate_features = [
        "Value",
        "cropland_ha_1000",
        "agricultural_land_ha_1000",
        "ag_value_per_area_int_usd",
        "faostat_production_mean",
        "faostat_food_security_mean",
        "faostat_food_balance_mean",
        "faostat_consumer_price_index_mean",
        "faostat_diet_affordability_mean",
        "faostat_sustainability_mean",
        "faostat_rural_employment_mean",
    ]
    feature_cols = [c for c in candidate_features if c in df.columns]

    if len(feature_cols) == 0:
        raise ValueError("Insufficient FAOSTAT feature columns for correlation-based extrapolation.")

    perf = build_correlation_regression_table(df, feature_cols, target_col="own_con2")
    best_feature = perf.iloc[0]["feature"]
    print(f"Best correlation feature for extrapolation: {best_feature}")

    train_sub = df[[best_feature, "own_con2"]].dropna().copy()
    intercept, slope = _fit_simple_linear(train_sub[best_feature].values, train_sub["own_con2"].values)
    if intercept is None or slope is None:
        raise ValueError(f"Unable to fit extrapolation regression on selected feature: {best_feature}")

    pred_mask = df["own_con2"].isna() & df[best_feature].notna()
    pred_values = intercept + slope * df.loc[pred_mask, best_feature].values
    df.loc[pred_mask, "own_con2"] = np.clip(pred_values, a_min=0, a_max=None)
    df["prediction_feature"] = pd.Series([None] * len(df), dtype="object")
    df.loc[pred_mask, "prediction_feature"] = best_feature

    df["own_con_source"] = np.where(
        original_has_own_con,
        "observed",
        np.where(original_has_own_con2, "interpolated", np.where(df["own_con2"].notna(), "extrapolated_correlation", "missing")),
    )

    out_cols = [
        "Country",
        "Year",
        "alpha-3",
        "own_con",
        "own_con2",
        "own_con_source",
        "prediction_feature",
        "wb_income",
    ] + feature_cols

    df_ext = df[out_cols].copy()
    df_ext.to_csv("./intermediates/data-own-consumption-extrapolation.csv", index=False)

    perf.to_csv("./results/extrapolation-correlation-regression.csv", index=False)
    render_markdown_table(perf, "./results/extrapolation-correlation-regression.md")

    # Keep legacy filenames for downstream compatibility.
    perf.to_csv("./results/extrapolation-model-performance.csv", index=False)
    render_markdown_table(perf, "./results/extrapolation-model-performance.md")

    selected = perf.iloc[[0]].copy()
    selected.to_csv("./results/extrapolation-selected-feature.csv", index=False)

    print("Extrapolated own consumption panel saved to './intermediates/data-own-consumption-extrapolation.csv'")
    print("Correlation/regression table saved to './results/extrapolation-correlation-regression.csv'")
    print("Correlation/regression markdown saved to './results/extrapolation-correlation-regression.md'")
    print("Selected extrapolation feature saved to './results/extrapolation-selected-feature.csv'")


if __name__ == "__main__":
    main()
