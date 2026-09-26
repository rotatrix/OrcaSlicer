set(_eigen_extra_flags "")
if (MSVC)
    set(_eigen_extra_flags "-DCMAKE_CXX_FLAGS:STRING=/bigobj")
endif ()
if (MSVC AND CMAKE_SYSTEM_PROCESSOR STREQUAL "ARM64")
    # Eigen's optional Fortran detection launches devenv and hangs on hosted ARM64.
    # MSVC provides no Fortran compiler; retain Eigen's normal no-Fortran path.
    list(APPEND _eigen_extra_flags "-DCMAKE_Fortran_COMPILER:FILEPATH=NOTFOUND")
endif ()

orcaslicer_add_cmake_project(Eigen
    URL https://gitlab.com/libeigen/eigen/-/archive/5.0.1/eigen-5.0.1.zip
    URL_HASH SHA256=0dbb1f9e3aaad66f352c03227d8c983f6f0b49e0b07e71a7300f4abcc01aee12
    CMAKE_ARGS "${_eigen_extra_flags}"
    DEPENDS dep_Boost dep_GMP dep_MPFR
)
