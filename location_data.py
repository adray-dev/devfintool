"""
location_data.py — Static US location data for sidebar dropdowns.
No API calls. Major cities and counties by state.
"""

STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming", "Washington D.C.",
]

CITIES_BY_STATE = {
    "Alabama": [
        "Auburn", "Birmingham", "Decatur", "Dothan", "Florence",
        "Hoover", "Huntsville", "Mobile", "Montgomery", "Tuscaloosa",
        "Jefferson County", "Madison County", "Mobile County", "Shelby County",
    ],
    "Alaska": [
        "Anchorage", "Fairbanks", "Juneau", "Kodiak", "Sitka",
        "Anchorage Municipality", "Fairbanks North Star Borough", "Matanuska-Susitna Borough",
    ],
    "Arizona": [
        "Avondale", "Chandler", "Flagstaff", "Gilbert", "Glendale",
        "Goodyear", "Mesa", "Peoria", "Phoenix", "Scottsdale",
        "Surprise", "Tempe", "Tucson", "Yuma",
        "Maricopa County", "Pima County", "Pinal County", "Yavapai County",
    ],
    "Arkansas": [
        "Bentonville", "Conway", "Fayetteville", "Fort Smith", "Jonesboro",
        "Little Rock", "North Little Rock", "Rogers", "Springdale",
        "Benton County", "Pulaski County", "Washington County",
    ],
    "California": [
        "Anaheim", "Bakersfield", "Berkeley", "Burbank", "Chula Vista",
        "Fresno", "Irvine", "Long Beach", "Los Angeles", "Oakland",
        "Ontario", "Pasadena", "Riverside", "Sacramento", "San Bernardino",
        "San Diego", "San Francisco", "San Jose", "Santa Ana", "Santa Monica",
        "Santa Rosa", "Stockton", "Torrance", "Ventura",
        "Alameda County", "Contra Costa County", "Fresno County",
        "Los Angeles County", "Orange County", "Riverside County",
        "Sacramento County", "San Bernardino County", "San Diego County",
        "San Francisco County", "San Mateo County", "Santa Clara County",
        "Ventura County",
    ],
    "Colorado": [
        "Arvada", "Aurora", "Boulder", "Colorado Springs", "Denver",
        "Fort Collins", "Greeley", "Lakewood", "Longmont", "Pueblo",
        "Thornton", "Westminster",
        "Adams County", "Arapahoe County", "Boulder County",
        "Denver County", "El Paso County", "Jefferson County", "Larimer County",
    ],
    "Connecticut": [
        "Bridgeport", "Danbury", "Greenwich", "Hartford", "New Haven",
        "New London", "Norwalk", "Stamford", "Waterbury",
        "Fairfield County", "Hartford County", "New Haven County",
    ],
    "Delaware": [
        "Dover", "Newark", "Wilmington",
        "Kent County", "New Castle County", "Sussex County",
    ],
    "Florida": [
        "Boca Raton", "Cape Coral", "Clearwater", "Coral Springs", "Fort Lauderdale",
        "Fort Myers", "Gainesville", "Hialeah", "Hollywood", "Jacksonville",
        "Miami", "Miami Beach", "Naples", "Orlando", "Palm Bay",
        "Pensacola", "Port St. Lucie", "Sarasota", "St. Petersburg",
        "Tallahassee", "Tampa", "West Palm Beach",
        "Broward County", "Duval County", "Hillsborough County",
        "Miami-Dade County", "Orange County", "Palm Beach County",
        "Pinellas County", "Sarasota County", "Seminole County",
    ],
    "Georgia": [
        "Albany", "Athens", "Atlanta", "Augusta", "Columbus",
        "Macon", "Marietta", "Roswell", "Savannah", "Warner Robins",
        "Cherokee County", "Clayton County", "Cobb County", "DeKalb County",
        "Fulton County", "Gwinnett County",
    ],
    "Hawaii": [
        "Hilo", "Honolulu", "Kailua", "Kapolei", "Pearl City",
        "Honolulu County", "Hawaii County", "Maui County",
    ],
    "Idaho": [
        "Boise", "Caldwell", "Coeur d'Alene", "Idaho Falls", "Meridian",
        "Nampa", "Pocatello", "Twin Falls",
        "Ada County", "Canyon County", "Kootenai County",
    ],
    "Illinois": [
        "Aurora", "Chicago", "Cicero", "Elgin", "Evanston",
        "Joliet", "Naperville", "Peoria", "Rockford", "Springfield",
        "Waukegan",
        "Cook County", "DuPage County", "Kane County", "Lake County",
        "McHenry County", "Will County",
    ],
    "Indiana": [
        "Bloomington", "Carmel", "Evansville", "Fishers", "Fort Wayne",
        "Hammond", "Indianapolis", "Muncie", "South Bend",
        "Allen County", "Hamilton County", "Lake County", "Marion County",
        "St. Joseph County",
    ],
    "Iowa": [
        "Ames", "Cedar Rapids", "Council Bluffs", "Davenport", "Des Moines",
        "Iowa City", "Sioux City", "Waterloo",
        "Black Hawk County", "Linn County", "Polk County", "Scott County",
    ],
    "Kansas": [
        "Kansas City", "Lawrence", "Olathe", "Overland Park", "Topeka", "Wichita",
        "Douglas County", "Johnson County", "Sedgwick County", "Wyandotte County",
    ],
    "Kentucky": [
        "Bowling Green", "Covington", "Lexington", "Louisville", "Owensboro",
        "Fayette County", "Jefferson County", "Kenton County",
    ],
    "Louisiana": [
        "Baton Rouge", "Kenner", "Lafayette", "Lake Charles",
        "Metairie", "New Orleans", "Shreveport",
        "Caddo Parish", "East Baton Rouge Parish", "Jefferson Parish",
        "Orleans Parish", "St. Tammany Parish",
    ],
    "Maine": [
        "Augusta", "Bangor", "Portland", "South Portland",
        "Cumberland County", "Kennebec County", "Penobscot County",
    ],
    "Maryland": [
        "Annapolis", "Baltimore", "Frederick", "Gaithersburg",
        "Rockville", "Silver Spring",
        "Anne Arundel County", "Baltimore County", "Howard County",
        "Montgomery County", "Prince George's County",
    ],
    "Massachusetts": [
        "Boston", "Brockton", "Cambridge", "Framingham", "Lowell",
        "New Bedford", "Newton", "Quincy", "Springfield", "Worcester",
        "Bristol County", "Essex County", "Middlesex County",
        "Norfolk County", "Plymouth County", "Suffolk County", "Worcester County",
    ],
    "Michigan": [
        "Ann Arbor", "Detroit", "Flint", "Grand Rapids", "Kalamazoo",
        "Lansing", "Livonia", "Sterling Heights", "Warren",
        "Kent County", "Macomb County", "Oakland County", "Washtenaw County",
        "Wayne County",
    ],
    "Minnesota": [
        "Bloomington", "Brooklyn Park", "Duluth", "Minneapolis",
        "Plymouth", "Rochester", "St. Paul",
        "Anoka County", "Dakota County", "Hennepin County",
        "Ramsey County", "Washington County",
    ],
    "Mississippi": [
        "Biloxi", "Gulfport", "Hattiesburg", "Jackson", "Meridian",
        "Hinds County", "Harrison County", "Rankin County",
    ],
    "Missouri": [
        "Columbia", "Independence", "Kansas City", "Lee's Summit",
        "O'Fallon", "Springfield", "St. Joseph", "St. Louis",
        "Boone County", "Clay County", "Jackson County",
        "St. Charles County", "St. Louis County",
    ],
    "Montana": [
        "Billings", "Bozeman", "Great Falls", "Helena", "Missoula",
        "Cascade County", "Gallatin County", "Missoula County", "Yellowstone County",
    ],
    "Nebraska": [
        "Bellevue", "Grand Island", "Lincoln", "Omaha",
        "Douglas County", "Lancaster County", "Sarpy County",
    ],
    "Nevada": [
        "Henderson", "Las Vegas", "North Las Vegas", "Reno", "Sparks",
        "Clark County", "Washoe County",
    ],
    "New Hampshire": [
        "Concord", "Dover", "Manchester", "Nashua",
        "Hillsborough County", "Merrimack County", "Rockingham County",
    ],
    "New Jersey": [
        "Atlantic City", "Camden", "Edison", "Elizabeth", "Jersey City",
        "Newark", "Paterson", "Trenton", "Woodbridge",
        "Bergen County", "Burlington County", "Camden County",
        "Essex County", "Hudson County", "Mercer County",
        "Middlesex County", "Monmouth County", "Morris County",
        "Ocean County", "Union County",
    ],
    "New Mexico": [
        "Albuquerque", "Las Cruces", "Rio Rancho", "Santa Fe",
        "Bernalillo County", "Doña Ana County", "Sandoval County",
    ],
    "New York": [
        "Albany", "Bronx", "Brooklyn", "Buffalo", "Manhattan",
        "Mount Vernon", "New Rochelle", "New York City", "Queens",
        "Rochester", "Staten Island", "Syracuse", "White Plains", "Yonkers",
        "Bronx County", "Brooklyn (Kings County)", "Erie County",
        "Manhattan (New York County)", "Monroe County", "Nassau County",
        "Onondaga County", "Queens County", "Staten Island (Richmond County)",
        "Suffolk County", "Westchester County",
    ],
    "North Carolina": [
        "Asheville", "Cary", "Chapel Hill", "Charlotte", "Durham",
        "Fayetteville", "Greensboro", "High Point", "Raleigh",
        "Wilmington", "Winston-Salem",
        "Buncombe County", "Cumberland County", "Durham County",
        "Forsyth County", "Guilford County", "Mecklenburg County",
        "Orange County", "Wake County",
    ],
    "North Dakota": [
        "Bismarck", "Fargo", "Grand Forks", "Minot",
        "Burleigh County", "Cass County", "Grand Forks County",
    ],
    "Ohio": [
        "Akron", "Cincinnati", "Cleveland", "Columbus", "Dayton",
        "Parma", "Toledo", "Youngstown",
        "Cuyahoga County", "Franklin County", "Hamilton County",
        "Lucas County", "Montgomery County", "Summit County",
    ],
    "Oklahoma": [
        "Broken Arrow", "Edmond", "Lawton", "Norman", "Oklahoma City",
        "Tulsa",
        "Cleveland County", "Oklahoma County", "Tulsa County",
    ],
    "Oregon": [
        "Beaverton", "Bend", "Eugene", "Gresham", "Hillsboro",
        "Medford", "Portland", "Salem",
        "Clackamas County", "Deschutes County", "Lane County",
        "Marion County", "Multnomah County", "Washington County",
    ],
    "Pennsylvania": [
        "Allentown", "Bethlehem", "Erie", "Philadelphia", "Pittsburgh",
        "Reading", "Scranton",
        "Allegheny County", "Bucks County", "Chester County",
        "Delaware County", "Lancaster County", "Montgomery County",
        "Philadelphia County",
    ],
    "Rhode Island": [
        "Cranston", "Pawtucket", "Providence", "Warwick", "Woonsocket",
        "Kent County", "Providence County",
    ],
    "South Carolina": [
        "Charleston", "Columbia", "Greenville", "Mount Pleasant",
        "North Charleston", "Rock Hill", "Spartanburg",
        "Berkeley County", "Charleston County", "Greenville County",
        "Horry County", "Lexington County", "Richland County",
        "Spartanburg County",
    ],
    "South Dakota": [
        "Aberdeen", "Rapid City", "Sioux Falls",
        "Lincoln County", "Minnehaha County", "Pennington County",
    ],
    "Tennessee": [
        "Chattanooga", "Clarksville", "Franklin", "Jackson",
        "Knoxville", "Memphis", "Murfreesboro", "Nashville",
        "Davidson County", "Hamilton County", "Knox County",
        "Rutherford County", "Shelby County", "Williamson County",
    ],
    "Texas": [
        "Arlington", "Austin", "Corpus Christi", "Dallas", "El Paso",
        "Fort Worth", "Frisco", "Garland", "Houston", "Irving",
        "Laredo", "Lubbock", "McKinney", "Plano", "San Antonio",
        "Bexar County", "Collin County", "Dallas County", "Denton County",
        "El Paso County", "Fort Bend County", "Harris County",
        "Hidalgo County", "Montgomery County", "Tarrant County",
        "Travis County", "Williamson County",
    ],
    "Utah": [
        "Ogden", "Orem", "Provo", "Salt Lake City", "Sandy",
        "St. George", "West Jordan", "West Valley City",
        "Davis County", "Salt Lake County", "Utah County",
        "Washington County", "Weber County",
    ],
    "Vermont": [
        "Burlington", "Essex", "Rutland", "South Burlington",
        "Chittenden County", "Rutland County", "Washington County",
    ],
    "Virginia": [
        "Alexandria", "Arlington", "Chesapeake", "Hampton",
        "Norfolk", "Newport News", "Richmond", "Roanoke",
        "Virginia Beach",
        "Arlington County", "Chesterfield County", "Fairfax County",
        "Henrico County", "Loudoun County", "Prince William County",
        "Virginia Beach (Independent City)",
    ],
    "Washington": [
        "Bellevue", "Bellingham", "Kent", "Kirkland", "Renton",
        "Seattle", "Spokane", "Tacoma", "Vancouver",
        "Clark County", "King County", "Pierce County",
        "Snohomish County", "Spokane County", "Thurston County",
    ],
    "West Virginia": [
        "Charleston", "Huntington", "Morgantown", "Parkersburg",
        "Cabell County", "Kanawha County", "Monongalia County",
    ],
    "Wisconsin": [
        "Green Bay", "Kenosha", "Madison", "Milwaukee",
        "Racine", "Waukesha",
        "Brown County", "Dane County", "Milwaukee County",
        "Outagamie County", "Racine County", "Waukesha County",
        "Winnebago County",
    ],
    "Wyoming": [
        "Casper", "Cheyenne", "Laramie",
        "Albany County", "Campbell County", "Laramie County", "Natrona County",
    ],
    "Washington D.C.": [
        "Washington D.C.",
    ],
}

# Flat sorted list of all unique cities/counties
ALL_CITIES = sorted(
    {city for cities in CITIES_BY_STATE.values() for city in cities}
)

# Reverse map: city → state (first match wins for duplicates like "Washington")
CITY_TO_STATE = {}
for _state, _cities in CITIES_BY_STATE.items():
    for _city in _cities:
        if _city not in CITY_TO_STATE:
            CITY_TO_STATE[_city] = _state
