ART_NAME=demo
OUT_DIR=output
all: ${OUT_DIR}/${ART_NAME}.pdf show
PFL_FLAGS=--shell-escape -output-directory=${OUT_DIR}
dirs:
	mkdir -p output
	mkdir -p figures
clean:
	rm -rf figures
	rm -rf output
	rm -rf *~*

pdf: ${OUT_DIR}/${ART_NAME}.pdf

show: ${OUT_DIR}/${ART_NAME}.pdf
	evince ${OUT_DIR}/${ART_NAME}.pdf &

figures/ipe_multi: ipe.multi/*
	mkdir -p figures
	( cd ipe.multi ; ./do_layers.sh )
	touch figures/ipe_multi

	

${OUT_DIR}/${ART_NAME}.pdf: dirs figures/ipe_multi  *.tex parts/*.tex
	pdflatex ${PFL_FLAGS} ${ART_NAME}.tex
	pdflatex ${PFL_FLAGS} ${ART_NAME}.tex
	pdflatex ${PFL_FLAGS} ${ART_NAME}.tex
	
